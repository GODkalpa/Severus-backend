import asyncio
from services.brain import get_pending_tasks, get_daily_biometrics, search_core_memory, get_expense_summary

async def main():
    print("Verifying action_items...")
    tasks = await get_pending_tasks()
    print(f"Tasks: {tasks[:50]}...")
    
    print("\nVerifying biometrics...")
    bio = await get_daily_biometrics()
    print(f"Biometrics: {bio[:50]}...")
    
    print("\nVerifying core_memory...")
    mem = await search_core_memory("test")
    print(f"Memory: {mem[:50]}...")
    
    print("\nVerifying financial_ledger...")
    exp = await get_expense_summary(7)
    print(f"Expenses: {exp[:50]}...")

if __name__ == "__main__":
    asyncio.run(main())
