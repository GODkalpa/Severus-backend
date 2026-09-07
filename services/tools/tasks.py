from services.db import supabase

async def add_task(task: str, priority: str = "normal", due_date: str | None = None) -> str:
    """
    Adds a new task to the action queue.
    """
    if not supabase:
        return "Action queue database is currently offline."

    try:
        priority = priority.lower() if priority else "normal"
        if priority not in {"low", "normal", "high"}:
            priority = "normal"

        data = {
            "task": task,
            "priority": priority,
            "due_date": due_date,
            "status": "pending"
        }
        supabase.table("action_items").insert(data).execute()
        return f"Successfully added '{task}' (Priority: {priority}) to your agenda."
    except Exception as e:
        print(f"Error adding task: {e}")
        return f"Could not save task to the queue: {str(e)}"


async def get_pending_tasks() -> str:
    """
    Retrieves all pending tasks from the action queue.
    """
    if not supabase:
        return "Action queue database is currently offline."

    try:
        response = (
            supabase.table("action_items")
            .select("*")
            .eq("status", "pending")
            .order("priority", desc=True)
            .order("created_at")
            .execute()
        )

        tasks = response.data or []
        if not tasks:
            return "Your agenda is completely clear. No pending tasks."

        summary = "Here is your current agenda:\n"
        for i, item in enumerate(tasks, 1):
            due_str = f" (Due: {item['due_date']})" if item.get("due_date") else ""
            summary += f"{i}. {item['task']} [{item['priority'].upper()}]{due_str}\n"

        return summary.strip()
    except Exception as e:
        print(f"Error getting pending tasks: {e}")
        return f"Trouble reading agenda: {str(e)}"


async def complete_task(task_search_term: str) -> str:
    """
    Marks a pending task as completed by matching its name.
    """
    if not supabase:
        return "Action queue database is currently offline."

    try:
        response = (
            supabase.table("action_items")
            .select("id, task")
            .eq("status", "pending")
            .ilike("task", f"%{task_search_term}%")
            .execute()
        )

        matches = response.data or []
        if not matches:
            return f"Could not find any pending task matching '{task_search_term}'."

        target = matches[0]
        supabase.table("action_items").update({"status": "completed"}).eq("id", target["id"]).execute()
        return f"Marked '{target['task']}' as completed."
    except Exception as e:
        print(f"Error completing task: {e}")
        return f"Error marking task completed: {str(e)}"


async def delete_task(task_search_term: str) -> str:
    """
    Removes a task from the agenda by matching its name.
    """
    if not supabase:
        return "Action queue database is currently offline."

    try:
        response = (
            supabase.table("action_items")
            .select("id, task")
            .ilike("task", f"%{task_search_term}%")
            .execute()
        )

        matches = response.data or []
        if not matches:
            return f"Could not find any task matching '{task_search_term}' to remove."

        target = matches[0]
        supabase.table("action_items").delete().eq("id", target["id"]).execute()
        return f"Removed '{target['task']}' from your tasks."
    except Exception as e:
        print(f"Error deleting task: {e}")
        return f"Error removing task: {str(e)}"
