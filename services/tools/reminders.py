from datetime import datetime, timezone, timedelta
from services.db import supabase

def _get_current_time_nepal():
    nepal_offset = timezone(timedelta(hours=5, minutes=45))
    return datetime.now(nepal_offset)

async def check_due_reminders() -> list[dict]:
    """
    Checks the reminders table for any tasks or timers that are due.
    """
    if not supabase:
        return []

    try:
        now = datetime.now(timezone.utc)
        response = supabase.table("reminders").select("*").eq("is_active", True).execute()
        all_active = response.data or []

        due = []
        for r in all_active:
            is_one_off = r.get("is_one_off", False)
            if is_one_off:
                due_at_str = r.get("due_at")
                if due_at_str:
                    due_at = datetime.fromisoformat(due_at_str.replace("Z", "+00:00"))
                    if now >= due_at:
                        due.append(r)
                continue

            lna = r.get("last_notified_at")
            if not lna:
                continue
            last = datetime.fromisoformat(lna.replace("Z", "+00:00"))
            interval = float(r.get("interval_hours", 2.0))
            if (now - last) >= timedelta(hours=interval):
                due.append(r)

        return due
    except Exception as e:
        print(f"Error checking reminders: {e}")
        return []


async def start_timer(minutes: int, seconds: int = 0, timer_text: str = "Timer is up!") -> str:
    """
    Starts a one-off timer.
    """
    if not supabase:
        return "Timer systems are currently unavailable."

    try:
        minutes = int(minutes)
        seconds = int(seconds) if seconds else 0
        duration_delta = timedelta(minutes=minutes, seconds=seconds)
        now_utc = datetime.now(timezone.utc)
        due_at = now_utc + duration_delta

        data = {
            "reminder_text": timer_text,
            "due_at": due_at.isoformat(),
            "is_one_off": True,
            "is_active": True,
            "last_notified_at": now_utc.isoformat()
        }
        supabase.table("reminders").insert(data).execute()
        time_display = f"{minutes} minute{'s' if minutes != 1 else ''}"
        if seconds > 0:
            time_display += f" and {seconds} second{'s' if seconds != 1 else ''}"
        return f"Starting a timer for {time_display} for '{timer_text}'."
    except Exception as e:
        print(f"Error starting timer: {e}")
        return f"Could not set timer: {str(e)}"


async def add_reminder(reminder_text: str, interval_hours: float) -> str:
    """
    Adds a recurring reminder to the database.
    """
    if not supabase:
        return "Reminder systems are offline."

    try:
        interval_hours = float(interval_hours)
        now_utc = datetime.now(timezone.utc)
        data = {
            "reminder_text": reminder_text,
            "interval_hours": interval_hours,
            "is_one_off": False,
            "is_active": True,
            "last_notified_at": now_utc.isoformat()
        }
        supabase.table("reminders").insert(data).execute()
        return f"Set a reminder for '{reminder_text}' every {interval_hours:g} hours."
    except Exception as e:
        print(f"Error adding reminder: {e}")
        return f"Could not set reminder: {str(e)}"


async def list_reminders() -> str:
    """
    Lists all active recurring reminders.
    """
    if not supabase:
        return "Reminder systems are offline."

    try:
        response = supabase.table("reminders").select("*").eq("is_active", True).execute()
        reminders = response.data or []

        if not reminders:
            return "You have no active recurring reminders."

        lines = ["Active reminders:"]
        for r in reminders:
            if r.get("is_one_off"):
                lines.append(f"- Timer: {r['reminder_text']} (Due: {r.get('due_at', 'soon')})")
            else:
                lines.append(f"- Recurring: {r['reminder_text']} (Every {r.get('interval_hours', 1):g} hours)")

        return "\n".join(lines)
    except Exception as e:
        print(f"Error listing reminders: {e}")
        return "Trouble accessing reminder list."


async def update_reminder_timestamp(reminder_ids: list[str]):
    """
    Updates the last_notified_at timestamp for the given reminder IDs.
    """
    if not supabase or not reminder_ids:
        return

    try:
        now_utc = datetime.now(timezone.utc).isoformat()
        for rid in reminder_ids:
            supabase.table("reminders").update({"last_notified_at": now_utc}).eq("id", rid).execute()
    except Exception as e:
        print(f"Error updating reminder timestamps: {e}")
