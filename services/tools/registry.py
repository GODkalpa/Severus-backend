import json
from typing import Any, Callable, Coroutine
from services.tools.weather import fetch_weather
from services.tools.search import search_the_web
from services.tools.tasks import add_task, get_pending_tasks, complete_task, delete_task
from services.tools.financial import log_expense, get_expense_summary
from services.tools.biometrics import log_biometric, log_calories, get_daily_biometrics
from services.tools.reminders import add_reminder, start_timer, list_reminders
from services.tools.memory import store_core_memory, search_core_memory

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "fetch_weather",
            "description": "Fetches current weather or short-range forecast for a given city or region.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or region name (e.g., 'Dharan', 'Kathmandu')."},
                    "when": {
                        "type": "string",
                        "description": "Timeframe: 'current', 'today', 'tomorrow', 'day after tomorrow', or weekday name."
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
            "description": "Searches the live web for recent information, news, events, prices, or general knowledge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The exact web search query."},
                    "max_results": {"type": "integer", "description": "Maximum number of results to fetch (1-5).", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Adds a new task or action item to the user's agenda.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description."},
                    "priority": {"type": "string", "enum": ["low", "normal", "high"], "description": "Priority level."},
                    "due_date": {"type": "string", "description": "Optional due date or time string."}
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pending_tasks",
            "description": "Lists all active/pending tasks from the user's agenda.",
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
            "description": "Marks an existing task as completed by matching its description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_search_term": {"type": "string", "description": "Search term matching the task."}
                },
                "required": ["task_search_term"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "Removes a task from the agenda entirely.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_search_term": {"type": "string", "description": "Search term matching the task."}
                },
                "required": ["task_search_term"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_expense",
            "description": "Logs an expense (amount, category, description) into the financial ledger.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Amount spent."},
                    "category": {"type": "string", "description": "Category (e.g. food, tech, transport, coffee)."},
                    "description": {"type": "string", "description": "Brief description of the purchase."}
                },
                "required": ["amount", "category", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_expense_summary",
            "description": "Retrieves total expenses and category breakdown over a given number of days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_back": {"type": "integer", "description": "Number of days back to summarize (default 7).", "default": 7}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_biometric",
            "description": "Logs a health/biometric metric (weight, water, sleep hours, blood pressure).",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_type": {"type": "string", "description": "Metric type (e.g. 'water', 'weight', 'sleep')."},
                    "value": {"type": "number", "description": "Numerical value."},
                    "unit": {"type": "string", "description": "Measurement unit (e.g. 'ml', 'kg', 'hrs')."},
                    "notes": {"type": "string", "description": "Optional notes or details."}
                },
                "required": ["metric_type", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_calories",
            "description": "Logs food consumed and calorie count into health vitals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "food_name": {"type": "string", "description": "Food item name."},
                    "calories": {"type": "integer", "description": "Number of calories."}
                },
                "required": ["food_name", "calories"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_biometrics",
            "description": "Summarizes health vitals recorded today.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_timer",
            "description": "Sets a one-off countdown timer that notifies when finished.",
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes": {"type": "integer", "description": "Duration in minutes."},
                    "seconds": {"type": "integer", "description": "Additional seconds.", "default": 0},
                    "timer_text": {"type": "string", "description": "Timer label or alert text.", "default": "Timer is up!"}
                },
                "required": ["minutes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_reminder",
            "description": "Adds a recurring reminder that fires every N hours.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_text": {"type": "string", "description": "What to be reminded of."},
                    "interval_hours": {"type": "number", "description": "Interval between alerts in hours."}
                },
                "required": ["reminder_text", "interval_hours"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "Lists all active recurring reminders and timers.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "store_core_memory",
            "description": "Stores user personal preferences, facts, or key personal information into the long-term memory vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_text": {"type": "string", "description": "Fact or preference to remember."},
                    "tags": {"type": "string", "description": "Tags (e.g. 'preference', 'identity', 'work').", "default": "general"}
                },
                "required": ["memory_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_core_memory",
            "description": "Searches the user's long-term memory vault for personal facts, preferences, or identity details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_query": {"type": "string", "description": "Search phrase or topic."}
                },
                "required": ["search_query"]
            }
        }
    }
]

TOOL_DISPATCH_MAP: dict[str, Callable[..., Coroutine[Any, Any, str]]] = {
    "fetch_weather": fetch_weather,
    "search_the_web": search_the_web,
    "add_task": add_task,
    "get_pending_tasks": get_pending_tasks,
    "complete_task": complete_task,
    "delete_task": delete_task,
    "log_expense": log_expense,
    "get_expense_summary": get_expense_summary,
    "log_biometric": log_biometric,
    "log_calories": log_calories,
    "get_daily_biometrics": get_daily_biometrics,
    "start_timer": start_timer,
    "add_reminder": add_reminder,
    "list_reminders": list_reminders,
    "store_core_memory": store_core_memory,
    "search_core_memory": search_core_memory,
}

async def dispatch_tool(function_name: str, function_args: dict) -> str:
    """
    Safely executes a requested tool by name with arguments.
    """
    func = TOOL_DISPATCH_MAP.get(function_name)
    if not func:
        return f"Error: Tool '{function_name}' is not recognized."

    try:
        # Cast parameters appropriately
        if function_name == "start_timer":
            if "minutes" in function_args:
                try: function_args["minutes"] = int(function_args["minutes"])
                except (ValueError, TypeError): pass
            if "seconds" in function_args:
                try: function_args["seconds"] = int(function_args["seconds"])
                except (ValueError, TypeError): pass
        elif function_name == "log_expense" and "amount" in function_args:
            try: function_args["amount"] = float(function_args["amount"])
            except (ValueError, TypeError): pass
        elif function_name == "log_biometric" and "value" in function_args:
            try: function_args["value"] = float(function_args["value"])
            except (ValueError, TypeError): pass
        elif function_name == "add_reminder" and "interval_hours" in function_args:
            try: function_args["interval_hours"] = float(function_args["interval_hours"])
            except (ValueError, TypeError): pass

        return await func(**function_args)
    except Exception as exc:
        print(f"Error executing tool '{function_name}': {exc}")
        return f"Error executing {function_name}: {str(exc)}"
