import asyncio
from services.brain import execute_raw_sql

async def main():
    # Attempt a query that MUST fail
    query = "SELECT non_existent_column_for_testing FROM action_items LIMIT 1;"
    result = await execute_raw_sql(query)
    print(f"Result for bad query: {result}")

if __name__ == "__main__":
    asyncio.run(main())
