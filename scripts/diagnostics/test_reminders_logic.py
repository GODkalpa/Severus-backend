
import asyncio
import os
from datetime import datetime, timedelta, timezone
import json
from supabase import create_client, Client
from dotenv import load_dotenv

# Load exactly like brain.py does
load_dotenv(".env.local", override=True)
load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL and SUPABASE_KEY must be set.")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_current_time_nepal():
    nepal_offset = timezone(timedelta(hours=5, minutes=45))
    return datetime.now(nepal_offset)

async def test_reminders():
    print("--- REMINDER SYSTEM TEST ---")
    
    # 1. Ensure a reminder exists
    reminder_text = "DRINK WATER (TEST)"
    interval = 0.01 # 36 seconds
    
    print(f"Adding test reminder: '{reminder_text}' every {interval} hours...")
    
    # Clean up old test reminders
    supabase.table("reminders").delete().eq("reminder_text", reminder_text).execute()
    
    # Add new
    now = get_current_time_nepal()
    past_time = now - timedelta(hours=0.1) # 6 minutes ago
    
    data = {
        "reminder_text": reminder_text,
        "interval_hours": interval,
        "last_reminded_at": past_time.isoformat(),
        "is_active": True
    }
    supabase.table("reminders").insert(data).execute()
    
    print("Test reminder added (simulated 6 mins ago).")
    
    # 2. Check if it's due
    print("Checking for due reminders...")
    # Import directly from the services.brain module (which is on the python path)
    import sys
    sys.path.append(os.getcwd())
    from services.brain import check_due_reminders, update_reminder_timestamp
    
    due = await check_due_reminders()
    found = False
    for r in due:
        if r["reminder_text"] == reminder_text:
            print(f"SUCCESS: Found due reminder: {r['reminder_text']}")
            found = True
            
            # 3. Test timestamp update
            print("Updating timestamp...")
            await update_reminder_timestamp([r["id"]])
            
            # 4. Verify update
            updated = supabase.table("reminders").select("last_reminded_at").eq("id", r["id"]).execute()
            updated_time_str = updated.data[0]["last_reminded_at"]
            # Handle possible trailing Z or offset
            updated_time = datetime.fromisoformat(updated_time_str.replace("Z", "+00:00"))
            
            # Convert past_time to same format if needed for comparison
            if updated_time.timestamp() > past_time.timestamp():
                print(f"SUCCESS: Timestamp updated to {updated_time}")
            else:
                print(f"FAILURE: Timestamp not updated. Original: {past_time}, Updated: {updated_time}")
    
    if not found:
        print("FAILURE: Test reminder was not found in due list.")
        print(f"Total due found: {len(due)}")
    
    # Cleanup
    supabase.table("reminders").delete().eq("reminder_text", reminder_text).execute()
    print("--- TEST COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(test_reminders())
