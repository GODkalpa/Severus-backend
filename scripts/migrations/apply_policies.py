import asyncio
from services.brain import execute_raw_sql

async def main():
    tables = ['action_items', 'biometrics', 'core_memory', 'financial_ledger']
    for table in tables:
        print(f"Applying RLS policy for {table}...")
        
        # Policy: Standard permissive policy for authenticated users in a personal assistant context
        sql = f"""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies 
                WHERE tablename = '{table}' 
                AND policyname = 'Allow authenticated full access'
            ) THEN
                CREATE POLICY "Allow authenticated full access" 
                ON public.{table} 
                FOR ALL 
                TO authenticated 
                USING (true)
                WITH CHECK (true);
            END IF;
        END $$;
        """
        
        result = await execute_raw_sql(sql)
        print(f"Result for {table}: {result}")

if __name__ == "__main__":
    asyncio.run(main())
