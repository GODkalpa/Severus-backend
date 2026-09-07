import asyncio
import json
from services.brain import execute_raw_sql

async def main():
    # Attempt to query the auth schema
    query = "SELECT id, email FROM auth.users;"
    result = await execute_raw_sql(query)
    print(f"Auth Users:\n{result}")

if __name__ == "__main__":
    asyncio.run(main())
