import asyncio
import os
import sys

# Ensure we're in the right directory for relative imports/env loading
# sys.path.append(os.getcwd())

from services.brain import execute_raw_sql, get_database_schema

async def main():
    print("Fetching internal Schema Summary...")
    schema = await get_database_schema()
    print(schema)
    
    print("\nQuerying REAL information_schema...")
    # Query all columns for the target tables
    query = """
    SELECT table_name, column_name 
    FROM information_schema.columns 
    WHERE table_schema = 'public' 
    AND table_name IN ('action_items', 'biometrics', 'core_memory', 'financial_ledger')
    ORDER BY table_name, ordinal_position;
    """
    
    # The brain.py execute_raw_sql function returns a string response in our project
    # We'll use it to see the data.
    result = await execute_raw_sql(query)
    print(f"Results:\n{result}")

if __name__ == "__main__":
    asyncio.run(main())
