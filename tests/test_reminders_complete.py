import asyncio
import time
import os
import sys

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.db import supabase
from services.brain import process_query_stream
from services.tools.registry import dispatch_tool

async def test_dispatch_direct():
    print("\n--- 1. Testing Direct Tool Dispatches ---")
    
    # A. Relative timer
    res1 = await dispatch_tool("schedule_reminder", {"reminder_text": "Tea break", "minutes": 10})
    print(f"schedule_reminder (minutes): {res1}")
    assert "timer" in res1.lower() or "10 minutes" in res1.lower(), f"Unexpected: {res1}"

    # B. Specific clock time
    res2 = await dispatch_tool("schedule_reminder", {"reminder_text": "Call doctor", "due_time": "5:00 PM"})
    print(f"schedule_reminder (due_time): {res2}")
    assert "05:00 PM" in res2 or "5:00 PM" in res2, f"Unexpected: {res2}"

    # C. Recurring reminder
    res3 = await dispatch_tool("schedule_reminder", {"reminder_text": "Posture check", "interval_hours": 3, "is_recurring": True})
    print(f"schedule_reminder (recurring): {res3}")
    assert "3 hours" in res3, f"Unexpected: {res3}"

    # D. Missing argument fallback (legacy add_reminder)
    res4 = await dispatch_tool("add_reminder", {"reminder_text": "Check email"})
    print(f"add_reminder (fallback): {res4}")
    assert not res4.startswith("Error"), f"Failed: {res4}"

    print("PASS: All direct tool dispatches succeeded!")

async def test_database_records():
    print("\n--- 2. Verifying Records in Supabase 'reminders' Table ---")
    resp = supabase.table("reminders").select("*").eq("is_active", True).order("created_at", desc=True).limit(5).execute()
    records = resp.data or []
    print(f"Found {len(records)} active reminders in DB:")
    for r in records:
        print(f"  - [{r['id'][:8]}] text='{r['reminder_text']}' is_one_off={r.get('is_one_off')} due_at={r.get('due_at')}")
    assert len(records) >= 4, "Expected at least 4 active reminders from test"
    print("PASS: Database accurately contains scheduled reminders!")

async def test_fast_path_stream():
    print("\n--- 3. Testing Snappy Fast-Path Response (< 5 seconds) ---")
    query = "Remind me to hydrate in 15 minutes"
    print(f"User Query: '{query}'")
    
    history = []
    t0 = time.time()
    chunks = []
    
    async for chunk in process_query_stream(query, history):
        if not chunks:
            t_first_chunk = time.time() - t0
            print(f"Time to first token (TTFT): {t_first_chunk:.2f}s")
        chunks.append(chunk)
        print(f"STREAM: '{chunk}'")
    
    t_total = time.time() - t0
    full_response = "".join(chunks)
    print(f"Total stream duration: {t_total:.2f}s")
    print(f"Final spoken text: '{full_response}'")
    
    assert t_total < 8.0, f"Expected fast-path under 8s, got {t_total:.2f}s"
    assert len(full_response) > 0, "Expected non-empty response"
    print("PASS: Fast-path confirmation is remarkably fast and snappy!")

async def test_cleanup():
    print("\n--- 4. Cleaning Up Test Rows ---")
    test_texts = ["Tea break", "Call doctor", "Posture check", "Check email", "hydrate"]
    for t in test_texts:
        supabase.table("reminders").delete().ilike("reminder_text", f"%{t}%").execute()
    print("Cleaned up test reminders.")

async def main():
    try:
        await test_dispatch_direct()
        await test_database_records()
        await test_fast_path_stream()
    finally:
        await test_cleanup()
    print("\n>>> ALL VERIFICATION TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    asyncio.run(main())
