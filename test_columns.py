import asyncio
from services.brain import execute_raw_sql

async def main():
    # Attempt to query a column name that might exist. 
    # If it fails, our RPC 'exec_sql' will likely return an error message containing the SQL error.
    query = "SELECT user_id FROM public.action_items LIMIT 1;"
    result = await execute_raw_sql(query)
    print(f"Result for user_id: {result}")
    
    query = "SELECT task FROM public.action_items LIMIT 1;"
    result = await execute_raw_sql(query)
    print(f"Result for task (known column): {result}")

if __name__ == "__main__":
    asyncio.run(main())
