import re
from datetime import datetime, timezone, timedelta
from services.db import supabase

def _get_current_time_nepal() -> datetime:
    nepal_offset = timezone(timedelta(hours=5, minutes=45))
    return datetime.now(nepal_offset)

def _parse_due_time(time_str: str) -> datetime:
    """
    Parses a natural language time/relative expression into a UTC datetime,
    using Dharan, Nepal (UTC+5:45) as the local reference.
    """
    now_local = _get_current_time_nepal()
    text = (time_str or "").lower().strip()

    # Relative duration: e.g. "10 minutes", "1.5 hours", "30 secs"
    rel_m = re.search(r"(\d+(?:\.\d+)?)\s*(minute|min|hour|hr|second|sec)", text)
    if rel_m:
        val = float(rel_m.group(1))
        unit = rel_m.group(2)
        if "min" in unit:
            delta = timedelta(minutes=val)
        elif "hour" in unit or "hr" in unit:
            delta = timedelta(hours=val)
        else:
            delta = timedelta(seconds=val)
        return (now_local + delta).astimezone(timezone.utc)

    # Clock time: e.g. "5 pm", "5:30 pm", "17:00", "at 9am"
    clock_m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if clock_m:
        hour = int(clock_m.group(1))
        minute = int(clock_m.group(2) or 0)
        ampm = clock_m.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if "tomorrow" in text or target <= now_local:
            target += timedelta(days=1)
        return target.astimezone(timezone.utc)

    # Fallback default: 15 minutes from now
    return (now_local + timedelta(minutes=15)).astimezone(timezone.utc)

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

async def schedule_reminder(
    reminder_text: str,
    minutes: int | float | None = None,
    seconds: int = 0,
    due_time: str | None = None,
    interval_hours: float | None = None,
    is_recurring: bool = False,
    **kwargs
) -> str:
    """
    Intelligent unified reminder handler. Supports:
    - Countdown timers (e.g. 10 minutes)
    - Specific clock time reminders (e.g. 'at 5:00 PM', 'tomorrow 9 AM')
    - Recurring reminders (e.g. every 2 hours)
    """
    if not supabase:
        return "Reminder systems are currently offline."

    reminder_text = (reminder_text or "Reminder").strip()
    now_utc = datetime.now(timezone.utc)

    try:
        # Case 1: Recurring reminder
        if is_recurring or (interval_hours is not None and interval_hours > 0 and not minutes and not due_time):
            interval = float(interval_hours or 2.0)
            data = {
                "reminder_text": reminder_text,
                "interval_hours": interval,
                "is_one_off": False,
                "is_active": True,
                "last_notified_at": now_utc.isoformat()
            }
            supabase.table("reminders").insert(data).execute()
            return f"Set a recurring reminder for '{reminder_text}' every {interval:g} hours."

        # Case 2: One-off timer via minutes/seconds
        if minutes is not None or seconds > 0:
            m = int(minutes or 0)
            s = int(seconds or 0)
            if m == 0 and s == 0:
                m = 10
            due_at = now_utc + timedelta(minutes=m, seconds=s)
            data = {
                "reminder_text": reminder_text,
                "due_at": due_at.isoformat(),
                "is_one_off": True,
                "is_active": True,
                "last_notified_at": now_utc.isoformat()
            }
            supabase.table("reminders").insert(data).execute()
            time_display = f"{m} minute{'s' if m != 1 else ''}"
            if s > 0:
                time_display += f" and {s} second{'s' if s != 1 else ''}"
            return f"Starting a timer for {time_display} for '{reminder_text}'."

        # Case 3: Due time expression (e.g. "at 5 pm", "tomorrow 9 am")
        if due_time:
            due_at = _parse_due_time(due_time)
            data = {
                "reminder_text": reminder_text,
                "due_at": due_at.isoformat(),
                "is_one_off": True,
                "is_active": True,
                "last_notified_at": now_utc.isoformat()
            }
            supabase.table("reminders").insert(data).execute()
            nepal_tz = timezone(timedelta(hours=5, minutes=45))
            due_nepal = due_at.astimezone(nepal_tz)
            formatted_time = due_nepal.strftime("%I:%M %p")
            return f"Reminder set for '{reminder_text}' at {formatted_time}."

        # Case 4: Text contains relative or clock time inside reminder_text itself
        # e.g., "Remind me to call John at 5 pm" or "take medicine in 20 minutes"
        time_match = re.search(r"\b(in\s+\d+\s*(?:min|minute|hour|hr)s?|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", reminder_text, re.IGNORECASE)
        if time_match:
            due_at = _parse_due_time(time_match.group(1))
            cleaned_text = re.sub(time_match.group(0), "", reminder_text, flags=re.IGNORECASE).strip()
            cleaned_text = re.sub(r"^(to|for|about)\s+", "", cleaned_text, flags=re.IGNORECASE).strip() or reminder_text
            data = {
                "reminder_text": cleaned_text,
                "due_at": due_at.isoformat(),
                "is_one_off": True,
                "is_active": True,
                "last_notified_at": now_utc.isoformat()
            }
            supabase.table("reminders").insert(data).execute()
            nepal_tz = timezone(timedelta(hours=5, minutes=45))
            due_nepal = due_at.astimezone(nepal_tz)
            formatted_time = due_nepal.strftime("%I:%M %p")
            return f"Reminder scheduled for '{cleaned_text}' at {formatted_time}."

        # Case 5: Default fallback (15 minutes)
        due_at = now_utc + timedelta(minutes=15)
        data = {
            "reminder_text": reminder_text,
            "due_at": due_at.isoformat(),
            "is_one_off": True,
            "is_active": True,
            "last_notified_at": now_utc.isoformat()
        }
        supabase.table("reminders").insert(data).execute()
        return f"Reminder set for '{reminder_text}' in 15 minutes."

    except Exception as e:
        print(f"Error scheduling reminder: {e}")
        return f"Could not schedule reminder: {str(e)}"

async def start_timer(
    minutes: int | float | None = 5,
    seconds: int = 0,
    timer_text: str = "Timer is up!",
    reminder_text: str | None = None,
    **kwargs
) -> str:
    """
    Starts a one-off countdown timer. Safe against missing arguments.
    """
    label = reminder_text or timer_text or "Timer"
    return await schedule_reminder(
        reminder_text=label,
        minutes=minutes or 5,
        seconds=seconds,
        is_recurring=False
    )

async def add_reminder(
    reminder_text: str = "Reminder",
    interval_hours: float | None = None,
    minutes: int | float | None = None,
    due_time: str | None = None,
    is_recurring: bool = False,
    **kwargs
) -> str:
    """
    Adds a reminder or timer. Coerces arguments safely.
    """
    return await schedule_reminder(
        reminder_text=reminder_text,
        minutes=minutes,
        due_time=due_time,
        interval_hours=interval_hours,
        is_recurring=is_recurring or (interval_hours is not None and interval_hours > 0 and not minutes and not due_time)
    )

async def list_reminders() -> str:
    """
    Lists all active recurring reminders and pending timers.
    """
    if not supabase:
        return "Reminder systems are offline."

    try:
        response = supabase.table("reminders").select("*").eq("is_active", True).execute()
        reminders = response.data or []

        if not reminders:
            return "You have no active reminders or timers."

        lines = ["Active reminders:"]
        nepal_tz = timezone(timedelta(hours=5, minutes=45))
        for r in reminders:
            text = r.get("reminder_text", "Untitled")
            if r.get("is_one_off"):
                due_at_str = r.get("due_at")
                if due_at_str:
                    due_dt = datetime.fromisoformat(due_at_str.replace("Z", "+00:00")).astimezone(nepal_tz)
                    lines.append(f"- Timer: {text} (Due at {due_dt.strftime('%I:%M %p')})")
                else:
                    lines.append(f"- Timer: {text}")
            else:
                interval = r.get("interval_hours", 1)
                lines.append(f"- Recurring: {text} (Every {interval:g} hours)")

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
