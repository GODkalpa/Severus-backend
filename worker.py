import asyncio
import time
from datetime import datetime, timezone, timedelta
from services.brain import supabase
from services.push_service import send_push_notification

async def get_active_reminders():
    """
    Retrieves all enabled reminders from the vault.
    """
    try:
        response = supabase.table("reminders").select("*").eq("is_active", True).execute()
        return response.data
    except Exception as e:
        print(f"❌ Error fetching reminders: {e}")
        return []

async def get_all_subscriptions():
    """
    Retrieves all registered push endpoints.
    """
    try:
        response = supabase.table("push_subscriptions").select("*").execute()
        return response.data
    except Exception as e:
        print(f"❌ Error fetching subscriptions: {e}")
        return []

async def update_reminder_time(reminder_id: str):
    """
    Updates the 'last_notified_at' timestamp once an alert is sent.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        supabase.table("reminders").update({"last_notified_at": now}).eq("id", reminder_id).execute()
        print(f"✅ Reminder {reminder_id} timestamp updated to {now}")
    except Exception as e:
        print(f"❌ Error updating reminder timestamp: {e}")

async def run_context_engine():
    """
    The main 24/7 background loop for Severus.
    """
    print("🧙‍♂️ [REVELIO] 24/7 Context Engine Initialized.")
    print("Severus is now watching over your vitals and tasks.")

    while True:
        try:
            reminders = await get_active_reminders()
            subscriptions = await get_all_subscriptions()

            if not reminders:
                print("Idle... No active reminders found.")
            elif not subscriptions:
                print("Skipping... No device subscriptions registered.")

            now = datetime.now(timezone.utc)

            for reminder in reminders:
                is_one_off = reminder.get("is_one_off", False)
                reminder_text = reminder.get("reminder_text", "Timer Alert")
                reminder_id = reminder.get("id")
                
                should_notify = False
                
                if is_one_off:
                    # Logic for one-off timers: check due_at
                    due_at_str = reminder.get("due_at")
                    if not due_at_str:
                        continue
                    due_at = datetime.fromisoformat(due_at_str.replace("Z", "+00:00"))
                    if now >= due_at:
                        should_notify = True
                        print(f"🚨 TIMER EXPIRED: '{reminder_text}' was due at {due_at}")
                else:
                    # Logic for recurring reminders: check interval
                    lna = reminder.get("last_notified_at") or reminder.get("lastNotifiedAt")
                    if not lna:
                        continue
                    last_notified = datetime.fromisoformat(lna.replace("Z", "+00:00"))
                    interval_hours = reminder.get("interval_hours", 2)
                    next_notification = last_notified + timedelta(hours=interval_hours)
                    
                    if now >= next_notification:
                        should_notify = True
                        print(f"🚨 RECURRING ALERT: '{reminder_text}' is due!")
                    else:
                        wait_minutes = (next_notification - now).total_seconds() / 60
                        print(f"⏳ '{reminder_text}' check: Wait {wait_minutes:.1f} more mins.")

                if should_notify:
                    # Notify every subscription
                    for sub in subscriptions:
                        sub_info = {
                            "endpoint": sub["endpoint"],
                            "keys": {
                                "p256dh": sub["p256dh"],
                                "auth": sub["auth"]
                            }
                        }
                        
                        send_push_notification(
                            subscription_info=sub_info,
                            message=reminder_text,
                            title="SEVERUS_ALERT"
                        )
                    
                    # Update status
                    if is_one_off:
                        # Deactivate one-off timers
                        supabase.table("reminders").update({"is_active": False, "last_notified_at": now.isoformat()}).eq("id", reminder_id).execute()
                        print(f"✅ Timer {reminder_id} completed and deactivated.")
                    else:
                        # Update timestamp for recurring
                        await update_reminder_time(reminder_id)

        except Exception as e:
            print(f"❌ Context engine error: {e}")

        # Sleep for 1 minute before next check
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(run_context_engine())
