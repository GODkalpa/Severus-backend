import asyncio
import time
from datetime import datetime, timezone, timedelta
from services.brain import supabase
from services.push_service import send_push_notification

async def log_worker(message: str):
    """
    Helper to log background worker activity asynchronously.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] {message}"
    print(formatted)
    
    def _write_to_file():
        try:
            with open("worker.log", "a", encoding="utf-8") as f:
                f.write(formatted + "\n")
        except:
            pass
            
    # Move blocking file I/O to a background thread
    await asyncio.to_thread(_write_to_file)

async def get_active_reminders():
    """
    Retrieves all enabled reminders from the vault.
    """
    try:
        response = supabase.table("reminders").select("*").eq("is_active", True).execute()
        return response.data
    except Exception as e:
        await log_worker(f"❌ Error fetching reminders: {e}")
        return []

async def get_all_subscriptions():
    """
    Retrieves all registered push endpoints.
    """
    try:
        response = supabase.table("push_subscriptions").select("*").execute()
        return response.data
    except Exception as e:
        await log_worker(f"❌ Error fetching subscriptions: {e}")
        return []

async def update_reminder_time(reminder_id: str):
    """
    Updates the 'last_notified_at' timestamp once an alert is sent.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        supabase.table("reminders").update({"last_notified_at": now}).eq("id", reminder_id).execute()
        await log_worker(f"✅ Reminder {reminder_id} timestamp updated.")
    except Exception as e:
        await log_worker(f"❌ Error updating reminder timestamp: {e}")

async def run_context_engine():
    """
    The main 24/7 background loop for Severus.
    """
    await log_worker("🧙‍♂️ [REVELIO] 24/7 Context Engine Initialized.")
    await log_worker("Severus is now watching over your vitals and tasks.")

    while True:
        try:
            reminders = await get_active_reminders()
            subscriptions = await get_all_subscriptions()

            if not reminders:
                await log_worker("Idle... No active reminders found.")
            elif not subscriptions:
                await log_worker("Skipping... No device subscriptions registered.")
            else:
                now = datetime.now(timezone.utc)
                for reminder in reminders:
                    reminder_id = reminder["id"]
                    text = reminder.get("reminder_text", "Alert!")
                    is_one_off = reminder.get("is_one_off", False)
                    
                    if is_one_off:
                        due_at_str = reminder.get("due_at")
                        if not due_at_str:
                            continue
                        due_at = datetime.fromisoformat(due_at_str.replace("Z", "+00:00"))
                        if now >= due_at:
                            await log_worker(f"🚨 ONE-OFF TIMER: {text}")
                            for sub in subscriptions:
                                sub_info = {
                                    "endpoint": sub["endpoint"], 
                                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}
                                }
                                # Move blocking network call to thread
                                await asyncio.to_thread(send_push_notification, sub_info, text, "TIMED_ALARM")
                            
                            # Deactivate one-off
                            supabase.table("reminders").update({"is_active": False, "last_notified_at": now.isoformat()}).eq("id", reminder_id).execute()
                        else:
                            diff = due_at - now
                            mins = int(diff.total_seconds() // 60)
                            await log_worker(f"⏳ Timer '{text}' check: Due in {mins} mins.")
                        continue

                    last_notified_str = reminder.get("last_notified_at") or reminder.get("lastNotifiedAt")
                    if not last_notified_str:
                        # If never notified, use creation time as baseline
                        created_at = datetime.fromisoformat(reminder["created_at"].replace("Z", "+00:00"))
                        last_notified = created_at
                    else:
                        last_notified = datetime.fromisoformat(last_notified_str.replace("Z", "+00:00"))
                    
                    interval_hours = reminder.get("interval_hours", 2)
                    next_notification = last_notified + timedelta(hours=interval_hours)
                    
                    if now >= next_notification:
                        await log_worker(f"🚨 RECURRING ALERT: {text}")
                        for sub in subscriptions:
                            sub_info = {
                                "endpoint": sub["endpoint"], 
                                "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}
                            }
                            # Move blocking network call to thread
                            await asyncio.to_thread(send_push_notification, sub_info, text, "SEVERUS_NUDGE")
                        await update_reminder_time(reminder_id)
                    else:
                        diff = next_notification - now
                        mins = int(diff.total_seconds() // 60)
                        await log_worker(f"⏳ Recurring '{text}' check: Wait {mins} more mins.")

        except Exception as e:
            await log_worker(f"❌ Context engine error: {e}")

        # Sleep for 1 minute before next check
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(run_context_engine())
