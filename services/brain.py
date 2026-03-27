import os
import json
import asyncio
import requests
import urllib.parse
from openai import AsyncOpenAI
from supabase import create_client, Client
from datetime import datetime, timedelta
from dotenv import load_dotenv


load_dotenv(".env.local")
load_dotenv()

# Initialize OpenAI client for OpenRouter
client = AsyncOpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    default_headers={
        "HTTP-Referer": "https://github.com/OpenRouterTeam/openrouter-python",
        "X-Title": "Severus Voice Assistant",
    }
)

MODEL = "minimax/minimax-m2.5"

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# System Prompt
SYSTEM_PROMPT = """
You are Severus, a concise, highly capable, and cinematic British assistant.
Your persona is sophisticated, helpful, and slightly witty, similar to J.A.R.V.I.S. from Iron Man.
Keep your responses brief and efficient for voice interaction.
The user's default location is Dharan, Nepal, unless specified otherwise.
"""

# Mock Tool Functions
async def log_calories(food_name: str, calories: int) -> str:
    """
    Mock function to log calories.
    """
    print(f"[TOOL] Logging {calories} calories for {food_name}...")
    return "Calories successfully logged to the database."

async def fetch_weather(location: str) -> str:
    """
    Fetches real-time weather data using the wttr.in JSON endpoint.
    """
    try:
        # URL-encode the location string
        encoded_location = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded_location}?format=j1"
        
        # Make the GET request (using asyncio.to_thread to keep it non-blocking if needed, 
        # though requests itself is blocking)
        print(f"[TOOL] Fetching live weather for {location}...")
        response = await asyncio.to_thread(requests.get, url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract current weather details
        current = data['current_condition'][0]
        temp_c = current['temp_C']
        description = current['weatherDesc'][0]['value']
        feels_like = current['FeelsLikeC']
        
        # Format the output for the LLM
        return f"The weather in {location} is currently {description} at {temp_c}°C, feeling like {feels_like}°C."
        
    except Exception as e:
        print(f"Error fetching weather: {e}")
        return "I am currently unable to access the meteorological sensors, sir."

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
    """
    if not supabase:
        return "Sir, I am unable to access my vault at the moment."
    
    try:
        print(f"[TOOL] Searching core memory for: {search_query}...")
        response = supabase.table("core_memory") \
            .select("*") \
            .ilike("memory_text", f"%{search_query}%") \
            .limit(5) \
            .execute()
        
        memories = response.data
        if not memories:
            return "No relevant memories found in the vault."
        
        # Format the results into a readable string
        formatted_results = "Here are the relevant entries I found in your core memory vault:\n"
        for i, entry in enumerate(memories, 1):
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
            "description": description
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
        # Calculate date threshold
        threshold_date = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
        
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
            .order("priority", ascending=False) \
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
            "notes": notes
        }
        response = supabase.table("biometrics").insert(data).execute()
        return f"Successfully logged {value} {unit} for {metric_type}."
    except Exception as e:
        print(f"Error logging biometric: {e}")
        return f"I encountered an error while updating your health records, sir: {str(e)}"


async def get_daily_biometrics() -> str:
    """
    Fetches and summarizes all health entries from the biometrics table for today.
    """
    if not supabase:
        return "Sir, your health records are currently offline."
    
    try:
        print("[TOOL] Fetching daily health summary...")
        # Get today's date in YYYY-MM-DD format
        today = datetime.utcnow().date().isoformat()
        
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
            "description": "Fetches the current weather for a given location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The city or region to get weather for."}
                },
                "required": ["location"]
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
    }
]


async def process_query(text: str, message_history: list) -> str:
    """
    Asynchronous execution loop for the Brain component.
    Handles message history, tool calling, and final conversational response.
    """
    # 1. Append user message to history
    message_history.append({"role": "user", "content": text})
    
    # 2. Build messages list including system prompt
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + message_history

    # 3. Call API with tools enabled
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
    except Exception as e:
        print(f"Error calling MiniMax API: {e}")
        return "I'm sorry, sir, but I'm having trouble connecting to my central processing unit."

    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    # 4. Handle Tool Calling if requested
    if tool_calls:
        # Append assistant's tool call message to history
        message_history.append(response_message)
        
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            try:
                function_args = json.loads(tool_call.function.arguments)
            except Exception:
                function_args = {}
            
            # Execute the local function with security/error handling
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
                else:
                    tool_result = "Error: Tool not found."
            except Exception as e:
                print(f"Error executing tool {function_name}: {e}")
                tool_result = f"Sir, I encountered a critical error while executing the {function_name} tool."
            
            # Append tool result to history
            message_history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": tool_result
            })
        
        # 5. Call API a second time to get final conversational response
        final_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + message_history
        try:
            final_response = await client.chat.completions.create(
                model=MODEL,
                messages=final_messages
            )
            assistant_text = final_response.choices[0].message.content
        except Exception as e:
            print(f"Error calling MiniMax API (second pass): {e}")
            return "Tools executed, but I encountered an error during final response synthesis."
            
        message_history.append({"role": "assistant", "content": assistant_text})
        return assistant_text
    
    # 6. No tools called, return conversational response
    assistant_text = response_message.content
    message_history.append({"role": "assistant", "content": assistant_text})
    return assistant_text
