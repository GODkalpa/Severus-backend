import asyncio
from services.brain import execute_raw_sql

async def main():
    # Query the first user id from auth.users (Supabase keeps users in the 'auth' schema)
    query = "SELECT id FROM auth.users LIMIT 1;"
    result = await execute_raw_sql(query)
    print(f"Current User IDs: {result}")

if __name__ == "__main__":
    asyncio.run(main())
