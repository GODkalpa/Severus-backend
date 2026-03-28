import asyncio
import json
from services.brain import execute_raw_sql

async def main():
    sql = """
    DO $$
    DECLARE
        table_name_var text;
        user_id_var uuid;
    BEGIN
        -- Get the first user id from auth.users to backfill
        SELECT id INTO user_id_var FROM auth.users ORDER BY created_at LIMIT 1;
        
        FOR table_name_var IN SELECT UNNEST(ARRAY['action_items', 'biometrics', 'core_memory', 'financial_ledger'])
        LOOP
            -- 1. Add user_id column if not exists
            EXECUTE format('ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users DEFAULT auth.uid()', table_name_var);
            
            -- 2. Backfill existing data
            IF user_id_var IS NOT NULL THEN
                EXECUTE format('UPDATE public.%I SET user_id = %L WHERE user_id IS NULL', table_name_var, user_id_var);
            END IF;

            -- 3. Drop old policy
            EXECUTE format('DROP POLICY IF EXISTS "Allow authenticated full access" ON public.%I', table_name_var);
            
            -- 4. Create new ownership policy
            -- NOTE: We use CASCADE or just drop if exists before CREATE. 
            -- The DROP handled it above.
            EXECUTE format('
                CREATE POLICY "Users can manage their own %I" 
                ON public.%I 
                FOR ALL 
                TO authenticated 
                USING (auth.uid() = user_id) 
                WITH CHECK (auth.uid() = user_id)', table_name_var, table_name_var);
        END LOOP;
    END $$;
    """
    
    print("Starting RLS policy refinement migration...")
    result = await execute_raw_sql(sql)
    print(f"Migration result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
