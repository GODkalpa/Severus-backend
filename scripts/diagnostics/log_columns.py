import asyncio
from services.brain import execute_raw_sql

async def main():
    tables = ['action_items', 'biometrics', 'core_memory', 'financial_ledger']
    with open('column_results.txt', 'w') as f:
        for table in tables:
            query = f"SELECT user_id FROM {table} LIMIT 1;"
            result = await execute_raw_sql(query)
            f.write(f"Table: {table} | Result: {result}\n")

if __name__ == "__main__":
    asyncio.run(main())
