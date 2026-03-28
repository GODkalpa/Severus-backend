import asyncio
from services.brain import execute_raw_sql

async def main():
    tables = ['biometrics', 'core_memory', 'financial_ledger']
    for table in tables:
        query = f"SELECT user_id FROM {table} LIMIT 1;"
        result = await execute_raw_sql(query)
        print(f"Result for {table} user_id: {result}")

if __name__ == "__main__":
    asyncio.run(main())
