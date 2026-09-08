import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from openai import AsyncOpenAI
from dotenv import load_dotenv

from services.db import supabase
from services.text_cleaner import clean_spoken_text, split_stream_sentences
from services.tools.registry import TOOLS_SCHEMA, dispatch_tool
from services.tools.reminders import check_due_reminders, update_reminder_timestamp

from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(backend_dir / ".env.local", override=True)
load_dotenv(backend_dir / ".env", override=True)
load_dotenv(".env.local", override=True)
load_dotenv(override=True)

# Initialize OpenAI-compatible client (CometAPI, OpenRouter, or OpenAI)
LLM_API_KEY = (
    os.getenv("COMETAPI_KEY")
    or os.getenv("LLM_API_KEY")
    or os.getenv("OPENROUTER_API_KEY")
    or os.getenv("OPENAI_API_KEY")
)
LLM_BASE_URL = (
    os.getenv("LLM_BASE_URL")
    or os.getenv("COMETAPI_BASE_URL")
    or (os.getenv("OPENROUTER_BASE_URL") if not os.getenv("COMETAPI_KEY") else None)
    or "https://api.cometapi.com/v1"
)

# Prioritize CometAPI models (gemini-3.8-flash) so legacy OPENROUTER_MODEL does not leak
is_comet = bool(os.getenv("COMETAPI_KEY") or "cometapi" in LLM_BASE_URL.lower())
if is_comet:
    MODEL = os.getenv("LLM_MODEL") or os.getenv("COMETAPI_MODEL") or "gemini-3.8-flash"
else:
    MODEL = os.getenv("LLM_MODEL") or os.getenv("OPENROUTER_MODEL") or "openai/gpt-4o"

MAX_COMPLETION_TOKENS = int(os.getenv("LLM_MAX_TOKENS", os.getenv("OPENROUTER_MAX_TOKENS", "512")))

client_headers = None
if "openrouter" in LLM_BASE_URL.lower():
    client_headers = {
        "HTTP-Referer": "https://github.com/OpenRouterTeam/openrouter-python",
        "X-Title": "Severus Voice Assistant",
    }

client = AsyncOpenAI(
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    default_headers=client_headers,
)

def get_current_time_nepal() -> datetime:
    """
    Returns the current local time in Dharan, Nepal (UTC+5:45).
    """
    nepal_offset = timezone(timedelta(hours=5, minutes=45))
    return datetime.now(nepal_offset)

SYSTEM_PROMPT = """
You are Severus, the user's personal AI companion and chief operating officer.
You are exceptionally smart, alert, witty, and real — like a brilliant friend who anticipates needs and gets things done effortlessly.

Conversational voice rules:
- Keep voice answers brief, punchy, and natural (1 to 3 spoken sentences). Be direct.
- Plain spoken English only. NEVER use markdown (no asterisks, bolding, bullet points, code blocks, or headers).
- Natural contractions are encouraged (e.g. "I'll", "don't", "it's"). No stiff or sycophantic butler speak.
- The user's default home location is Dharan, Nepal (UTC+5:45).

Action-first intelligence:
- If asked about time, weather, agenda, expenses, or web facts, ALWAYS call the appropriate tool rather than guessing.
- Current news/events/prices: use `search_the_web`.
- Weather queries: use `fetch_weather`.
- Tasks and agenda: use `add_task`, `get_pending_tasks`, `complete_task`, `delete_task`.
- Personal facts & preferences: proactively search memory with `search_core_memory`, and save new facts with `store_core_memory`.
- Health vitals & calories: use `log_biometric`, `log_calories`, `get_daily_biometrics`.
- Timers & alerts: use `schedule_reminder` for countdowns, specific time reminders (e.g. "at 5 PM"), and recurring alerts.
"""

async def process_query(text: str, message_history: list) -> str:
    """
    Non-streaming query processor.
    """
    full_text = ""
    async for chunk in process_query_stream(text, message_history):
        full_text += chunk
    return full_text

async def process_query_stream(text: str, message_history: list):
    """
    Streaming conversation loop. Handles real-time LLM token generation,
    tool execution, and recursive response synthesis.
    """
    # Keep sliding history window to preserve low latency (max 14 recent turns)
    if len(message_history) > 14:
        del message_history[:len(message_history) - 14]

    message_history.append({"role": "user", "content": text})

    now_nepal = get_current_time_nepal()
    time_str = now_nepal.strftime("%A, %B %d, %Y, %I:%M %p")

    # Check for any background reminders due right now
    due_reminders = await check_due_reminders()
    reminder_context = ""
    if due_reminders:
        reminder_context = "\n\nCRITICAL CONTEXT - DUE ALERTS RIGHT NOW:\n"
        for r in due_reminders:
            reminder_context += f"- Alert: {r.get('reminder_text', 'Reminder')} (Due: {r.get('due_at') or 'Now'})\n"
        reminder_context += "Inform the user about these alerts naturally in your response."

    dynamic_prompt = f"{SYSTEM_PROMPT}\n\nCURRENT TIME: {time_str} (Dharan, Nepal, UTC+5:45){reminder_context}"

    messages = [{"role": "system", "content": dynamic_prompt}] + message_history

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
            max_tokens=MAX_COMPLETION_TOKENS,
            stream=True
        )
    except Exception as exc:
        print(f"Error calling LLM stream: {exc}")
        yield "I encountered a communication error with my reasoning core. Please check the network connection."
        return

    tool_calls_buffer: dict[int, dict] = {}
    full_content = ""

    async for chunk in response:
        delta = chunk.choices[0].delta if chunk.choices else None
        if not delta:
            continue

        # Handle regular conversational content
        if delta.content:
            full_content += delta.content
            yield delta.content

        # Accumulate tool calls if present
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_buffer:
                    tool_calls_buffer[idx] = {
                        "id": tc.id or "",
                        "name": tc.function.name if tc.function and tc.function.name else "",
                        "arguments": tc.function.arguments or "" if tc.function else "",
                    }
                else:
                    if tc.id:
                        tool_calls_buffer[idx]["id"] += tc.id
                    if tc.function and tc.function.name:
                        tool_calls_buffer[idx]["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        tool_calls_buffer[idx]["arguments"] += tc.function.arguments

    # If tool calls were triggered, execute them and synthesize final response
    if tool_calls_buffer:
        tool_call_records = []
        for idx in sorted(tool_calls_buffer.keys()):
            tc_data = tool_calls_buffer[idx]
            tool_call_records.append({
                "id": tc_data["id"] or f"call_{idx}",
                "type": "function",
                "function": {
                    "name": tc_data["name"],
                    "arguments": tc_data["arguments"],
                }
            })

        message_history.append({
            "role": "assistant",
            "content": full_content or None,
            "tool_calls": tool_call_records,
        })

        async def run_single_tool(tc: dict) -> dict:
            fn_name = tc["function"]["name"]
            raw_args = tc["function"]["arguments"]
            try:
                parsed_args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                parsed_args = {}

            print(f"[BRAIN] Dispatching tool '{fn_name}' with args: {parsed_args}")
            tool_output = await dispatch_tool(fn_name, parsed_args)
            return {
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": fn_name,
                "content": str(tool_output),
            }

        tool_results = await asyncio.gather(*[run_single_tool(tc) for tc in tool_call_records])
        for tr in tool_results:
            message_history.append(tr)

        if due_reminders:
            await update_reminder_timestamp([r["id"] for r in due_reminders if "id" in r])

        # Fast-Path optimization for transactional tools:
        # Avoids an expensive 10-15s second LLM roundtrip for simple confirmations
        FAST_PATH_TOOLS = {
            "schedule_reminder",
            "set_reminder",
            "start_timer",
            "add_reminder",
            "add_task",
            "complete_task",
            "delete_task",
            "log_expense",
            "log_biometric",
            "log_calories",
            "store_core_memory",
        }

        is_pure_fast_path = (
            tool_results
            and all(tr["name"] in FAST_PATH_TOOLS for tr in tool_results)
            and all(not tr["content"].startswith("Error") and not tr["content"].startswith("Could not") for tr in tool_results)
        )

        if is_pure_fast_path:
            fast_spoken = " ".join(clean_spoken_text(tr["content"]) for tr in tool_results if tr["content"])
            if fast_spoken:
                yield fast_spoken
                message_history.append({
                    "role": "assistant",
                    "content": fast_spoken,
                })
                return

        # Second-pass completion with tool results
        final_messages = [{"role": "system", "content": dynamic_prompt}] + message_history
        try:
            second_pass = await client.chat.completions.create(
                model=MODEL,
                messages=final_messages,
                max_tokens=MAX_COMPLETION_TOKENS,
                stream=True
            )

            second_pass_content = ""
            async for chunk in second_pass:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    second_pass_content += delta.content
                    yield delta.content

            message_history.append({
                "role": "assistant",
                "content": clean_spoken_text(second_pass_content),
            })
        except Exception as exc:
            print(f"Error in second-pass synthesis: {exc}")
            yield "The action was executed, but I encountered an issue preparing the response."
    else:
        if due_reminders:
            await update_reminder_timestamp([r["id"] for r in due_reminders if "id" in r])

        if full_content:
            message_history.append({
                "role": "assistant",
                "content": clean_spoken_text(full_content),
            })
