import asyncio
from services.brain import execute_raw_sql

async def main():
    sql = """
    DO $$
    DECLARE
        table_name_var text;
    BEGIN
        FOR table_name_var IN SELECT UNNEST(ARRAY['action_items', 'biometrics', 'core_memory', 'financial_ledger'])
        LOOP
            -- 1. Drop existing user policies
            EXECUTE format('DROP POLICY IF EXISTS "Users can manage their own %I" ON public.%I', table_name_var, table_name_var);
            
            -- 2. Create optimized ownership policy using (SELECT auth.uid())
            -- This wrapping enables the "initplan" optimization in Postgres.
            EXECUTE format('
                CREATE POLICY "Users can manage their own %I" 
                ON public.%I 
                FOR ALL 
                TO authenticated 
                USING ((SELECT auth.uid()) = user_id) 
                WITH CHECK ((SELECT auth.uid()) = user_id)', table_name_var, table_name_var);
        END LOOP;
    END $$;
    """
    
    print("Starting RLS performance optimization migration...")
    result = await execute_raw_sql(sql)
    print(f"Optimization Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
