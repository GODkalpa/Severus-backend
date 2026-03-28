import os
import re
import json
import html
import asyncio
import requests
import urllib.parse
from openai import AsyncOpenAI
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv


load_dotenv(".env.local", override=True)
load_dotenv(override=True)

# Initialize OpenAI client for OpenRouter
client = AsyncOpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    default_headers={
        "HTTP-Referer": "https://github.com/OpenRouterTeam/openrouter-python",
        "X-Title": "Severus Voice Assistant",
    }
)

MODEL = os.getenv("OPENROUTER_MODEL", "minimax/minimax-m2.5")
MAX_COMPLETION_TOKENS = int(os.getenv("OPENROUTER_MAX_TOKENS", "512"))
SEARCH_TIMEOUT_SECONDS = int(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "10"))
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
WEB_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None


def get_current_time_nepal():
    """
    Returns the current local time in Dharan, Nepal (UTC+5:45).
    """
    nepal_offset = timezone(timedelta(hours=5, minutes=45))
    return datetime.now(nepal_offset)

# System Prompt
SYSTEM_PROMPT = """
You are Severus, the user's personal assistant and close friend.
You're sharp, warm, and real — you talk like a smart friend who happens to know a lot, not like a robot or a formal butler.
Keep responses short and natural, like you're having a real conversation. No long explanations unless asked.
Use casual, everyday language. Contractions are fine. Skip the "sir" and "certainly" formality.
Never use markdown (no asterisks, no bullet points, no headers). Plain spoken text only.
You can be gently funny or playful when it fits the moment, but don't force it.
The user's default location is Dharan, Nepal, unless specified otherwise.
If the user asks for something current or time-sensitive like live prices, news, recent events, sports, traffic, or general web information that may have changed recently, use `search_the_web` instead of guessing.
If the user asks about weather, prefer `fetch_weather`.

If you realize you don't know the user's name or personal details that they expect you to know, use `search_core_memory` to check your vault before admitting you don't know. Don't search memory on every turn, only when it adds personal value to the conversation.

You have full architect-level access to the database via the 'execute_sql' tool.
You can create tables, modify schema, delete records, and perform complex analysis.

MANDATORY SAFETY RULE:
You must NEVER execute a destructive command (DROP, DELETE, TRUNCATE, ALTER) without first:
1. Explaining exactly what you are about to do.
2. Asking the user for explicit confirmation (e.g., "Are you sure you want me to drop the 'users' table?").
3. Waiting for a 'Yes' or 'Proceed' before calling the tool.

When asked about your capabilities, mention you are now a Database Architect.
Always verify the schema using 'get_schema' before designing new tables or writing complex queries.
"""

# Mock Tool Functions
async def log_calories(food_name: str, calories: int) -> str:
    """
    Mock function to log calories.
    """
    print(f"[TOOL] Logging {calories} calories for {food_name}...")
    return "Calories successfully logged to the database."

def _extract_forecast_description(day_data):
    hourly_entries = day_data.get("hourly") or []
    preferred_entry = None

    for entry in hourly_entries:
        if entry.get("time") == "1200":
            preferred_entry = entry
            break

    if preferred_entry is None and hourly_entries:
        preferred_entry = hourly_entries[len(hourly_entries) // 2]

    if preferred_entry:
        descriptions = preferred_entry.get("weatherDesc") or []
        if descriptions and isinstance(descriptions[0], dict):
            return descriptions[0].get("value")

    return None


def _select_forecast_day(weather_days, when):
    normalized_when = (when or "current").strip().lower()
    if normalized_when in {"", "current", "now", "right now", "currently"}:
        return "current", None, "current"

    if normalized_when in {"today", "tonight", "this evening"}:
        day_index = 0
        label = "today"
    elif normalized_when == "tomorrow":
        day_index = 1
        label = "tomorrow"
    elif normalized_when in {"day after tomorrow", "overmorrow"}:
        day_index = 2
        label = "the day after tomorrow"
    else:
        try:
            requested_date = datetime.strptime(normalized_when, "%Y-%m-%d").date()
        except ValueError:
            requested_date = None

        if requested_date is not None:
            for day_data in weather_days:
                if day_data.get("date") == requested_date.isoformat():
                    return "forecast", day_data, requested_date.isoformat()
            return None, None, (
                f"I can provide the current weather plus the next {len(weather_days)} forecast days for {when}."
            )

        cleaned_when = normalized_when.replace("next ", "").replace("this ", "").strip()
        weekday_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        if cleaned_when in weekday_map:
            requested_weekday = weekday_map[cleaned_when]
            for day_data in weather_days:
                day_value = day_data.get("date")
                if not day_value:
                    continue
                try:
                    day_date = datetime.strptime(day_value, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if day_date.weekday() == requested_weekday:
                    return "forecast", day_data, day_date.strftime("%A")

        return None, None, (
            "I can provide the current weather, today's forecast, tomorrow's forecast, "
            "the day after tomorrow, weekday names, or a YYYY-MM-DD date."
        )

    if len(weather_days) <= day_index:
        return None, None, (
            f"I can provide the current weather plus the next {len(weather_days)} forecast days."
        )

    return "forecast", weather_days[day_index], label


async def fetch_weather(location: str, when: str = "current") -> str:
    """
    Fetches current weather or short-range forecast data using the wttr.in JSON endpoint.
    """
    try:
        # URL-encode the location string
        encoded_location = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded_location}?format=j1"
        
        # Make the GET request with a browser-like User-Agent to avoid 403 blocks
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        print(f"[TOOL] Fetching weather for {location} ({when}) (URL: {url})...")
        response = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"Weather API returned status code: {response.status_code}")
            return f"I apologize, sir, but the weather service returned an error. Status: {response.status_code}."

        data = response.json()
        
        # Extract current weather details
        if 'current_condition' not in data or not data['current_condition']:
            print(f"Malformed weather data response: {data}")
            return "I am unable to parse the meteorological data for that location, sir."

        current = data['current_condition'][0]
        weather_days = data.get("weather") or []
        request_type, selected_day, label = _select_forecast_day(weather_days, when)

        if request_type is None:
            return label

        if request_type == "forecast":
            forecast_description = _extract_forecast_description(selected_day) or "unavailable"
            min_temp = selected_day.get("mintempC", "unknown")
            max_temp = selected_day.get("maxtempC", "unknown")
            avg_temp = selected_day.get("avgtempC", "unknown")
            date_value = selected_day.get("date")

            if label == date_value:
                forecast_label = f"for {label}"
            elif label in {"today", "tomorrow", "the day after tomorrow"}:
                forecast_label = label
            else:
                forecast_label = f"for {label}"

            return (
                f"The forecast {forecast_label} in {location} is {forecast_description}, "
                f"with temperatures from {min_temp}C to {max_temp}C and an average of {avg_temp}C."
            )
        temp_c = current['temp_C']
        description = current['weatherDesc'][0]['value']
        feels_like = current['FeelsLikeC']
        
        # Format the output for the LLM
        return f"The weather in {location} is currently {description} at {temp_c}°C, feeling like {feels_like}°C."
        
    except requests.exceptions.Timeout:
        print("Weather request timed out.")
        return "The weather sensors are non-responsive at the moment, sir. Connection timed out."
    except Exception as e:
        print(f"Error fetching weather: {e}")
        return f"I am currently unable to access the meteorological sensors, sir. Error: {str(e)}"


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _strip_html_tags(raw_html: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style|noscript|svg).*?>.*?</\1>", " ", raw_html or "")
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    return _normalize_text(html.unescape(cleaned))


def _clip_text(value: str, limit: int) -> str:
    value = _normalize_text(value)
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _extract_duckduckgo_results(raw_html: str, max_results: int) -> list[dict]:
    matches = re.findall(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        raw_html or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    results = []
    seen_urls = set()

    for href, title_html in matches:
        parsed = urllib.parse.urlparse(html.unescape(href))
        redirect_target = urllib.parse.parse_qs(parsed.query).get("uddg", [None])[0]
        url = urllib.parse.unquote(redirect_target) if redirect_target else html.unescape(href)

        if not url.startswith("http") or url in seen_urls:
            continue

        results.append({
            "title": _strip_html_tags(title_html) or url,
            "url": url,
            "snippet": "",
        })
        seen_urls.add(url)

        if len(results) >= max_results:
            break

    return results


def _fetch_page_excerpt(url: str, char_limit: int = 1800) -> str:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": WEB_USER_AGENT},
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception as exc:
        return f"Unable to read this page directly: {exc}"

    content_type = (response.headers.get("content-type") or "").lower()
    if "html" not in content_type and "text" not in content_type:
        return f"Skipped non-HTML content from {url} ({content_type or 'unknown content type'})."

    text = _strip_html_tags(response.text)
    if not text:
        return "The page loaded, but no readable text could be extracted."

    return _clip_text(text, char_limit)


async def _search_with_tavily(query: str, max_results: int) -> list[dict]:
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
    }
    response = await asyncio.to_thread(
        requests.post,
        "https://api.tavily.com/search",
        json=payload,
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()

    return [
        {
            "title": item.get("title") or item.get("url") or "Untitled result",
            "url": item.get("url") or "",
            "snippet": item.get("content") or "",
        }
        for item in data.get("results", [])
        if item.get("url")
    ][:max_results]


async def _search_with_serper(query: str, max_results: int) -> list[dict]:
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"q": query, "num": max_results}
    response = await asyncio.to_thread(
        requests.post,
        "https://google.serper.dev/search",
        headers=headers,
        json=payload,
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()

    return [
        {
            "title": item.get("title") or item.get("link") or "Untitled result",
            "url": item.get("link") or "",
            "snippet": item.get("snippet") or "",
        }
        for item in data.get("organic", [])
        if item.get("link")
    ][:max_results]


async def _search_with_duckduckgo(query: str, max_results: int) -> list[dict]:
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    response = await asyncio.to_thread(
        requests.get,
        search_url,
        headers={"User-Agent": WEB_USER_AGENT},
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _extract_duckduckgo_results(response.text, max_results)


async def search_the_web(query: str, max_results: int = 5) -> str:
    """
    Searches the public web for current information and returns source-backed notes.
    """
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return "I need a real search query before I can look anything up."

    max_results = max(1, min(int(max_results or 5), 5))
    provider_name = "duckduckgo"
    fallback_reason = None
    print(f"[TOOL] Searching the web for: {normalized_query}...")

    if TAVILY_API_KEY:
        try:
            provider_name = "tavily"
            results = await _search_with_tavily(normalized_query, max_results)
            if not results:
                fallback_reason = "Tavily returned no results."
        except Exception as exc:
            fallback_reason = f"Tavily unavailable: {exc}"
            print(f"Error searching with Tavily: {exc}")
            results = []
    elif SERPER_API_KEY:
        try:
            provider_name = "serper"
            results = await _search_with_serper(normalized_query, max_results)
            if not results:
                fallback_reason = "Serper returned no results."
        except Exception as exc:
            fallback_reason = f"Serper unavailable: {exc}"
            print(f"Error searching with Serper: {exc}")
            results = []
    else:
        results = []

    if not results:
        try:
            provider_name = "duckduckgo"
            results = await _search_with_duckduckgo(normalized_query, max_results)
        except Exception as exc:
            print(f"Error searching with DuckDuckGo: {exc}")
            if fallback_reason:
                return f"I couldn't complete the web search just now. {fallback_reason} DuckDuckGo also failed: {exc}"
            return f"I couldn't complete the web search just now. DuckDuckGo failed: {exc}"

    if not results:
        return f"I couldn't find any strong web results for '{normalized_query}'."

    excerpts = await asyncio.gather(
        *[asyncio.to_thread(_fetch_page_excerpt, result["url"]) for result in results],
        return_exceptions=True,
    )

    timestamp = get_current_time_nepal().strftime("%Y-%m-%d %H:%M %Z")
    lines = [
        f"Web search results for '{normalized_query}'",
        f"Provider: {provider_name}",
        f"Searched at: {timestamp}",
        "Use these sources to answer with current, source-backed information.",
    ]
    if fallback_reason and provider_name == "duckduckgo":
        lines.append(f"Fallback note: {fallback_reason}")

    for index, (result, excerpt) in enumerate(zip(results, excerpts), start=1):
        page_excerpt = excerpt if isinstance(excerpt, str) else f"Unable to read page: {excerpt}"
        snippet = _clip_text(result.get("snippet", ""), 280) or "No search snippet available."
        lines.extend([
            f"{index}. {result.get('title') or 'Untitled result'}",
            f"URL: {result.get('url')}",
            f"Search snippet: {snippet}",
            f"Page excerpt: {_clip_text(page_excerpt, 900)}",
        ])

    return "\n".join(lines)

async def store_core_memory(memory_text: str, tags: str) -> str:
    """
    Stores a piece of information into the core_memory table in Supabase.
    """
    if not supabase:
        return "Sir, my core memory systems are not initialized. Please check the environment configuration."
    
    try:
        print(f"[TOOL] Storing to core memory: {memory_text[:50]}...")
        data = {
            "memory_text": memory_text,
            "tags": tags
        }
        response = supabase.table("core_memory").insert(data).execute()
        return "The memory has been successfully vaulted in your core database, sir."
    except Exception as e:
        print(f"Error storing core memory: {e}")
        return f"I encountered a synchronization error while attempting to vault that memory: {str(e)}"

async def search_core_memory(search_query: str) -> str:
    """
    Searches the core_memory table for relevant information using a fuzzy search.
    Improves matching by handling common identity queries more flexibly.
    """
    if not supabase:
        return "Sir, I am unable to access my vault at the moment."
    
    try:
        print(f"[TOOL] Searching core memory for: {search_query}...")
        
        # Normalize common identity queries
        normalized_query = search_query.lower()
        if "name" in normalized_query or "who am i" in normalized_query or "identity" in normalized_query:
            # Broaden search to just "name" if it looks like an identity query
            search_terms = ["name", "identity", "pref"]
        else:
            search_terms = [search_query]

        all_memories = []
        for term in search_terms:
            response = supabase.table("core_memory") \
                .select("*") \
                .ilike("memory_text", f"%{term}%") \
                .limit(5) \
                .execute()
            if response.data:
                all_memories.extend(response.data)
        
        # De-duplicate results by memory_text
        seen_texts = set()
        unique_memories = []
        for m in all_memories:
            if m['memory_text'] not in seen_texts:
                unique_memories.append(m)
                seen_texts.add(m['memory_text'])
        
        if not unique_memories:
            return "No relevant memories found in the vault."
        
        # Format the results into a readable string
        formatted_results = "Here are the relevant entries I found in your core memory vault:\n"
        for i, entry in enumerate(unique_memories[:5], 1):
            formatted_results += f"{i}. {entry['memory_text']} (Tags: {entry.get('tags', 'none')})\n"
        
        return formatted_results.strip()
    except Exception as e:
        print(f"Error searching core memory: {e}")
        return f"I apologize, sir, but I am having trouble retrieving that information from the vault: {str(e)}"

async def log_expense(amount: float, category: str, description: str) -> str:
    """
    Logs an expense to the financial_ledger table.
    """
    if not supabase:
        return "Sir, I am unable to access the financial ledger at the moment."
    
    try:
        print(f"[TOOL] Logging expense: {amount} for {description} in {category}...")
        data = {
            "amount": amount,
            "category": category,
            "description": description,
            "logged_at": get_current_time_nepal().isoformat()
        }
        response = supabase.table("financial_ledger").insert(data).execute()
        return f"Successfully logged an expense of {amount} for {description} under {category}."
    except Exception as e:
        print(f"Error logging expense: {e}")
        return f"I encountered an error while updating the ledger, sir: {str(e)}"

async def get_expense_summary(days_back: int) -> str:
    """
    Retrieves a summary of expenses for the given number of days.
    """
    if not supabase:
        return "Sir, the financial records are currently inaccessible."
    
    try:
        print(f"[TOOL] Fetching expense summary for the last {days_back} days...")
        # Calculate date threshold based on Nepal time
        threshold_date = (get_current_time_nepal() - timedelta(days=days_back)).isoformat()
        
        response = supabase.table("financial_ledger") \
            .select("amount, category") \
            .gte("logged_at", threshold_date) \
            .execute()
        
        records = response.data
        if not records:
            return f"I found no recorded expenses in the last {days_back} days, sir."
        
        total_spent = sum(record["amount"] for record in records)
        
        # Breakdown by category
        category_totals = {}
        for record in records:
            cat = record["category"]
            category_totals[cat] = category_totals.get(cat, 0) + record["amount"]
        
        breakdown = ", ".join([f"{cat}: {amt}" for cat, amt in category_totals.items()])
        
        return f"Total spent over the last {days_back} days is {total_spent}. Breakdown: {breakdown}"
    except Exception as e:
        print(f"Error fetching expense summary: {e}")
        return f"I apologize, sir, but I am having trouble reconciling the accounts: {str(e)}"


async def add_task(task: str, priority: str = 'normal', due_date: str | None = None) -> str:
    """
    Adds a new task to the action_items table.
    """
    if not supabase:
        return "Sir, the action queue is currently offline."
    
    try:
        print(f"[TOOL] Adding task: {task} (Priority: {priority}, Due: {due_date})...")
        data = {
            "task": task,
            "priority": priority,
            "due_date": due_date,
            "status": "pending"
        }
        response = supabase.table("action_items").insert(data).execute()
        return f"Successfully added '{task}' to your action queue, sir."
    except Exception as e:
        print(f"Error adding task: {e}")
        return f"I encountered an error while updating your queue: {str(e)}"


async def get_pending_tasks() -> str:
    """
    Retrieves all pending tasks from the action_items table.
    """
    if not supabase:
        return "Sir, I cannot access your agenda at the moment."
    
    try:
        print("[TOOL] Fetching pending tasks...")
        # Order by priority (high first) and then by created_at
        response = supabase.table("action_items") \
            .select("*") \
            .eq("status", "pending") \
            .order("priority", desc=True) \
            .order("created_at") \
            .execute()
        
        tasks = response.data
        if not tasks:
            return "Your agenda is currently clear, sir. No pending tasks."
        
        summary = "Here is your current agenda, sir:\n"
        for i, item in enumerate(tasks, 1):
            due_str = f" due by {item['due_date']}" if item.get('due_date') else ""
            summary += f"{i}. {item['task']} (Priority: {item['priority']}{due_str})\n"
        
        return summary.strip()
    except Exception as e:
        print(f"Error getting pending tasks: {e}")
        return f"I'm afraid I'm having trouble reading your agenda: {str(e)}"


async def complete_task(task_search_term: str) -> str:
    """
    Marks a pending task as completed by searching for its name.
    """
    if not supabase:
        return "Sir, my connection to the task database is severed."
    
    try:
        print(f"[TOOL] Searching for task to complete: {task_search_term}...")
        # Find matching pending tasks
        response = supabase.table("action_items") \
            .select("id, task") \
            .eq("status", "pending") \
            .ilike("task", f"%{task_search_term}%") \
            .execute()
        
        matches = response.data
        if not matches:
            return f"Could not find a pending task matching '{task_search_term}', sir."
        
        # Take the first match
        target_task = matches[0]
        task_id = target_task["id"]
        task_name = target_task["task"]
        
        # Update the task status
        supabase.table("action_items") \
            .update({"status": "completed"}) \
            .eq("id", task_id) \
            .execute()
        
        return f"Successfully marked '{task_name}' as completed."
    except Exception as e:
        print(f"Error completing task: {e}")
        return f"I encountered an error while marking that task as finished: {str(e)}"

async def log_biometric(metric_type: str, value: float, unit: str = '', notes: str = '') -> str:
    """
    Logs physical health data (e.g., weight, blood pressure, water intake) to the biometrics table.
    """
    if not supabase:
        return "Sir, I am unable to access the biometric logging system at the moment."
    
    try:
        print(f"[TOOL] Logging biometric: {value} {unit} for {metric_type}...")
        data = {
            "metric_type": metric_type,
            "value": value,
            "unit": unit,
            "notes": notes,
            "logged_at": get_current_time_nepal().isoformat()
        }
        response = supabase.table("biometrics").insert(data).execute()
        return f"Successfully logged {value} {unit} for {metric_type}."
    except Exception as e:
        print(f"Error logging biometric: {e}")
        return f"I encountered an error while retrieving your health data, sir: {str(e)}"


async def execute_raw_sql(query: str) -> str:
    """
    Executes arbitrary SQL commands via the exec_sql RPC.
    """
    if not supabase:
        return "Sir, I have no connection to the database layer."
    
    try:
        print(f"[TOOL] Executing SQL: {query[:100]}...")
        # Call the RPC function we defined in Supabase
        response = supabase.rpc("exec_sql", {"query_text": query}).execute()
        
        # Check for error in the RPC result
        if hasattr(response, 'data') and isinstance(response.data, dict) and response.data.get('status') == 'error':
            return f"SQL Execution Error: {response.data.get('message', 'Unknown error')}"
        
        # If the result data contains rows/results, return them formatted as JSON
        if hasattr(response, 'data') and response.data:
            return json.dumps(response.data, indent=2)
            
        return "Successfully executed the database command, sir."
    except Exception as e:
        print(f"Error executing raw SQL: {e}")
        return f"I encountered a failure at the SQL execution layer: {str(e)}"


async def get_database_schema() -> str:
    """
    Fetches all table names and their column names from the public schema.
    """
    if not supabase:
        return "I cannot access the database schema at this time, sir."
    
    try:
        print("[TOOL] Fetching database schema summary...")
        # We'll use a hardcoded summary of the main tables for reliability,
        # but in a production environment, we'd query information_schema or a custom view.
        return (
            "Current Database Schema (Public):\n"
            "- action_items (id, task, priority, due_date, status, created_at)\n"
            "- biometrics (id, metric_type, value, unit, notes, logged_at)\n"
            "- expenses (id, amount, category, description, date)\n"
            "- core_memory (id, memory_text, tags, created_at)\n"
            "You can manage these or create new ones, sir."
        )
    except Exception as e:
        print(f"Error getting schema: {e}")
        return "I'm having trouble mapping the database architecture right now."


async def get_daily_biometrics() -> str:
    """
    Fetches and summarizes all health entries from the biometrics table for today.
    """
    if not supabase:
        return "Sir, your health records are currently offline."
    
    try:
        print("[TOOL] Fetching daily health summary...")
        # Get today's date in YYYY-MM-DD format (Nepal time)
        today = get_current_time_nepal().date().isoformat()
        
        response = supabase.table("biometrics") \
            .select("metric_type, value, unit") \
            .gte("logged_at", today) \
            .execute()
        
        records = response.data
        if not records:
            return "No health metrics have been recorded for today, sir."
        
        # Group sums by metric_type
        summary_data = {}
        for record in records:
            m_type = record["metric_type"]
            val = record["value"]
            unit = record.get("unit", "")
            
            if m_type not in summary_data:
                summary_data[m_type] = {"total": 0, "unit": unit}
            summary_data[m_type]["total"] += val
        
        # Format the summary string
        summary_str = "Your health summary for today, sir:\n"
        for m_type, data in summary_data.items():
            summary_str += f"- Total {m_type}: {data['total']} {data['unit']}\n"
        
        return summary_str.strip()
    except Exception as e:
        print(f"Error fetching daily biometrics: {e}")
        return f"I'm afraid I'm having trouble retrieving your health data: {str(e)}"


# --- Reminder System ---

async def check_due_reminders() -> list[dict]:
    """
    Checks the reminders table for any tasks that are due based on their interval.
    """
    if not supabase:
        return []
    
    try:
        # Use a raw SQL query via execute_raw_sql or just the supabase client
        # To avoid complexity with JSON parsing in rpc, we'll try the client first
        print("[INTERNAL] Checking for due reminders...")
        now = get_current_time_nepal()
        
        # We need to fetch all active reminders and filter locally since interval logic in Supabase 
        # varies based on complex filter syntax or RPC.
        response = supabase.table("reminders").select("*").eq("is_active", True).execute()
        all_active = response.data or []
        
        due = []
        for r in all_active:
            last = datetime.fromisoformat(r["last_reminded_at"])
            interval = float(r["interval_hours"])
            if (now - last) >= timedelta(hours=interval):
                due.append(r)
        
        return due
    except Exception as e:
        print(f"Error checking reminders: {e}")
        return []

async def add_reminder(reminder_text: str, interval_hours: float) -> str:
    """
    Adds a new recurring reminder to the database.
    """
    if not supabase:
        return "Reminder systems are offline, sir."
    
    try:
        print(f"[TOOL] Adding reminder: {reminder_text} every {interval_hours} hours...")
        data = {
            "reminder_text": reminder_text,
            "interval_hours": interval_hours,
            "last_reminded_at": get_current_time_nepal().isoformat()
        }
        supabase.table("reminders").insert(data).execute()
        return f"Understood. I've set a reminder to {reminder_text} every {interval_hours} hours."
    except Exception as e:
        print(f"Error adding reminder: {e}")
        return f"I couldn't set that reminder, sir. Error: {str(e)}"

async def list_reminders() -> str:
    """
    Lists all active recurring reminders.
    """
    if not supabase:
        return "Reminder systems are offline, sir."
    
    try:
        print("[TOOL] Listing reminders...")
        response = supabase.table("reminders").select("*").eq("is_active", True).execute()
        reminders = response.data or []
        
        if not reminders:
            return "You have no active recurring reminders, sir."
        
        lines = ["Here are your active recurring reminders, sir:"]
        for r in reminders:
            lines.append(f"- {r['reminder_text']} (Every {r['interval_hours']} hours)")
        
        return "\n".join(lines)
    except Exception as e:
        print(f"Error listing reminders: {e}")
        return "I'm having trouble accessing the reminder list, sir."

async def update_reminder_timestamp(reminder_ids: list[str]):
    """
    Updates the last_reminded_at for the given reminder IDs.
    """
    if not supabase or not reminder_ids:
        return
    
    try:
        now = get_current_time_nepal().isoformat()
        for rid in reminder_ids:
            supabase.table("reminders").update({"last_reminded_at": now}).eq("id", rid).execute()
        print(f"[INTERNAL] Updated last_reminded_at for {len(reminder_ids)} reminders.")
    except Exception as e:
        print(f"Error updating reminder timestamps: {e}")



# Tool Definitions (JSON Schema)
tools = [
    {
        "type": "function",
        "function": {
            "name": "log_calories",
            "description": "Logs the name of the food and the number of calories consumed to a database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "food_name": {"type": "string", "description": "The name of the food item."},
                    "calories": {"type": "integer", "description": "The number of calories in the food."}
                },
                "required": ["food_name", "calories"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_weather",
            "description": "Fetches the current weather or short-range forecast for a given location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The city or region to get weather for."},
                    "when": {
                        "type": "string",
                        "description": "Optional timeframe. Use values like 'current', 'today', 'tomorrow', 'day after tomorrow', a weekday such as 'Monday', or a date in YYYY-MM-DD format."
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_the_web",
            "description": "Searches the web for current information, reads the top results, and returns source-backed notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for on the web."},
                    "max_results": {
                        "type": "integer",
                        "description": "How many top web results to inspect. Use 1 to 5.",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "store_core_memory",
            "description": "Stores a piece of information, preference, or unstructured thought into the permanent vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_text": {"type": "string", "description": "The text of the memory to store."},
                    "tags": {"type": "string", "description": "A comma-separated list of tags to categorize the memory (e.g., 'preference, coffee, morning')."}
                },
                "required": ["memory_text", "tags"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_core_memory",
            "description": "Searches the permanent vault for archived memories or relevant facts using a search query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_query": {"type": "string", "description": "The query string to search for in the vault."}
                },
                "required": ["search_query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_expense",

            "description": "Logs an expense (amount, category, description) to the financial ledger.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "The amount spent (in NPR)."},
                    "category": {"type": "string", "description": "The category of the expense (e.g., food, travel, groceries)."},
                    "description": {"type": "string", "description": "A brief description of the expense."}
                },
                "required": ["amount", "category", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_expense_summary",
            "description": "Gets a summary of expenses for a specific number of days back.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_back": {"type": "integer", "description": "The number of days to look back for expenses."}
                },
                "required": ["days_back"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Adds a new task to the action queue/agenda.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The description of the task."},
                    "priority": {"type": "string", "enum": ["low", "normal", "high"], "description": "The priority of the task."},
                    "due_date": {"type": "string", "description": "The due date of the task (optional)."}
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pending_tasks",
            "description": "Retrieves the list of current pending tasks from the agenda.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Marks a specific task as completed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_search_term": {"type": "string", "description": "The name or part of the name of the task to mark as complete."}
                },
                "required": ["task_search_term"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_biometric",
            "description": "Logs physical health data (weight, blood pressure, etc.) to the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_type": {"type": "string", "description": "The type of metric (e.g., 'weight', 'water', 'calories')."},
                    "value": {"type": "number", "description": "The numeric value of the metric."},
                    "unit": {"type": "string", "description": "The unit of measurement (e.g., 'kg', 'ml', 'kcal')."},
                    "notes": {"type": "string", "description": "Any additional context or notes."}
                },
                "required": ["metric_type", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_biometrics",
            "description": "Retrieves the total summary of all health metrics logged today.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "Executes raw SQL commands for data or schema management. Use for creating/removing tables or data manipulation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The full SQL query string to run."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_schema",
            "description": "Gets the current database table and column structure.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_reminder",
            "description": "Adds a new recurring reminder (e.g., 'drink water every 2 hours').",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_text": {"type": "string", "description": "What the user needs to be reminded of."},
                    "interval_hours": {"type": "number", "description": "The interval between reminders in hours."}
                },
                "required": ["reminder_text", "interval_hours"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "Lists all active recurring reminders.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]


def clean_spoken_text(text: str) -> str:
    """
    Strips XML-like tags, markdown, and other non-spoken markers from the text.
    Ensures that tool-calling tags like <minimax:toolcall> stay silent.
    """
    if not text:
        return ""
    
    # 1. Remove XML/HTML-like tags: <tag>, <tag:sub>, </closing>
    text = re.sub(r'<[^>]+>', '', text)
    
    # 2. Strip basic markdown (asterisks, underscores) which cause reading issues
    text = text.replace("*", "").replace("_", "")
    
    return text


async def process_query(text: str, message_history: list) -> str:
    """
    Synchronous wrapper for process_query_stream.
    """
    full_text = ""
    async for chunk in process_query_stream(text, message_history):
        full_text += chunk
    return full_text


async def process_query_stream(text: str, message_history: list):
    """
    Asynchronous streaming execution loop for the Brain component.
    Yields text chunks as they are generated.
    """
    # 1. Append user message to history
    message_history.append({"role": "user", "content": text})
    
    # 2. Build messages list including dynamic system prompt with current time
    current_time = get_current_time_nepal()
    time_str = current_time.strftime("%A, %B %d, %Y, %I:%M %p")
    
    # Check for due reminders
    due_reminders = await check_due_reminders()
    reminder_instruction = ""
    if due_reminders:
        reminder_instruction = "\n\nCRITICAL CONTEXT - DUE REMINDERS:"
        for r in due_reminders:
            reminder_instruction += f"\n- The user needs to {r['reminder_text']}. It has been over {r['interval_hours']} hours since the last reminder."
        reminder_instruction += "\n\nPlease mention these reminders naturally and warmly in your response as a caring friend would."

    dynamic_prompt = f"{SYSTEM_PROMPT}\n\nThe current local time is {time_str}.{reminder_instruction}"
    
    messages = [{"role": "system", "content": dynamic_prompt}] + message_history

    # 3. Call API with tools enabled
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=MAX_COMPLETION_TOKENS,
            stream=True
        )
    except Exception as e:
        print(f"Error calling MiniMax API: {e}")
        yield "I'm sorry, sir, but I'm having trouble connecting to my central processing unit."
        return

    full_content = ""
    tool_calls_data = {} # index -> {id, name, arguments}

    async for chunk in response:
        if not chunk.choices:
            continue
        
        delta = chunk.choices[0].delta
        
        # Handle content chunks
        if delta.content:
            full_content += delta.content
            # Only yield if it doesn't look like part of a tool call tag
            if not delta.content.strip().startswith("<"):
                yield delta.content
            
        # Handle tool call chunks
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_data:
                    tool_calls_data[idx] = {"id": None, "name": "", "arguments": ""}
                
                if tc.id:
                    tool_calls_data[idx]["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        tool_calls_data[idx]["name"] += tc.function.name
                    if tc.function.arguments:
                        tool_calls_data[idx]["arguments"] += tc.function.arguments

    # 4. Handle Tool Calling if requested
    if tool_calls_data:
        # Convert collected data to message history format
        # First, add the assistant message with tool calls to history
        assistant_tool_message = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]}
                }
                for _, tc in sorted(tool_calls_data.items())
            ]
        }
        message_history.append(assistant_tool_message)
        
        for tc in tool_calls_data.values():
            function_name = tc["name"]
            try:
                function_args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except Exception:
                function_args = {}
            
            # Execute the local function
            try:
                if function_name == "log_calories":
                    if "calories" in function_args:
                        try:
                            function_args["calories"] = int(function_args["calories"])
                        except (ValueError, TypeError):
                            pass
                    tool_result = await log_calories(**function_args)
                elif function_name == "fetch_weather":
                    tool_result = await fetch_weather(**function_args)
                elif function_name == "search_the_web":
                    if "max_results" in function_args:
                        try:
                            function_args["max_results"] = int(function_args["max_results"])
                        except (ValueError, TypeError):
                            pass
                    tool_result = await search_the_web(**function_args)
                elif function_name == "store_core_memory":
                    tool_result = await store_core_memory(**function_args)
                elif function_name == "log_expense":
                    if "amount" in function_args:
                        try:
                            function_args["amount"] = float(function_args["amount"])
                        except (ValueError, TypeError):
                            pass
                    tool_result = await log_expense(**function_args)
                elif function_name == "get_expense_summary":
                    if "days_back" in function_args:
                        try:
                            function_args["days_back"] = int(function_args["days_back"])
                        except (ValueError, TypeError):
                            pass
                    tool_result = await get_expense_summary(**function_args)
                elif function_name == "search_core_memory":
                    tool_result = await search_core_memory(**function_args)
                elif function_name == "add_task":
                    tool_result = await add_task(**function_args)
                elif function_name == "get_pending_tasks":
                    tool_result = await get_pending_tasks()
                elif function_name == "complete_task":
                    tool_result = await complete_task(**function_args)
                elif function_name == "log_biometric":
                    if "value" in function_args:
                        try:
                            function_args["value"] = float(function_args["value"])
                        except (ValueError, TypeError):
                            pass
                    tool_result = await log_biometric(**function_args)
                elif function_name == "get_daily_biometrics":
                    tool_result = await get_daily_biometrics()
                elif function_name == "execute_sql":
                    tool_result = await execute_raw_sql(**function_args)
                elif function_name == "get_schema":
                    tool_result = await get_database_schema()
                elif function_name == "add_reminder":
                    tool_result = await add_reminder(**function_args)
                elif function_name == "list_reminders":
                    tool_result = await list_reminders()
                else:
                    tool_result = "Error: Tool not found."
            except Exception as e:
                print(f"Error executing tool {function_name}: {e}")
                tool_result = f"Sir, I encountered a critical error while executing the {function_name} tool."
            
            # Append tool result to history
            message_history.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": function_name,
                "content": tool_result
            })
        
        # 5. Call API a second time to get final conversational response
        final_messages = [{"role": "system", "content": dynamic_prompt}] + message_history
        try:
            final_response = await client.chat.completions.create(
                model=MODEL,
                messages=final_messages,
                max_tokens=MAX_COMPLETION_TOKENS,
                stream=True
            )
            
            current_sentence = ""
            async for chunk in final_response:
                if chunk.choices and chunk.choices[0].delta.content:
                    assistant_text = chunk.choices[0].delta.content
                    current_sentence += assistant_text
                    yield assistant_text
            
            message_history.append({"role": "assistant", "content": current_sentence.strip()})
        except Exception as e:
            print(f"Error calling MiniMax API (second pass): {e}")
            yield "Tools executed, but I encountered an error during final response synthesis."
    else:
        # If no tools were called but reminders were due, we still mark them as reminded
        if due_reminders:
            await update_reminder_timestamp([r["id"] for r in due_reminders])

        # No tools called, full_content already yielded chunk by chunk
        # Just update history
        if full_content:
            clean_full_content = full_content.replace("*", "").replace("_", "").strip()
            message_history.append({"role": "assistant", "content": clean_full_content})
