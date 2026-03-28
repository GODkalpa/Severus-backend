import asyncio
from services.brain import execute_raw_sql

async def setup_reminders_table():
    sql = """
    CREATE TABLE IF NOT EXISTS public.reminders (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        reminder_text TEXT NOT NULL,
        interval_hours NUMERIC NOT NULL,
        last_reminded_at TIMESTAMPTZ DEFAULT now(),
        is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMPTZ DEFAULT now()
    );

    -- Apply RLS if needed (already handled by apply_policies.py logic usually, but let's be explicit)
    ALTER TABLE public.reminders ENABLE ROW LEVEL SECURITY;

    DO $$ 
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies 
            WHERE tablename = 'reminders' 
            AND policyname = 'Allow authenticated full access'
        ) THEN
            CREATE POLICY "Allow authenticated full access" 
            ON public.reminders 
            FOR ALL 
            TO authenticated 
            USING (true)
            WITH CHECK (true);
        END IF;
    END $$;
    """
    print("Creating reminders table...")
    result = await execute_raw_sql(sql)
    print(f"Result: {result}")

    # Seed the water reminder
    seed_sql = """
    INSERT INTO public.reminders (reminder_text, interval_hours, last_reminded_at)
    VALUES ('Drink some water', 2.0, now() - interval '2 hours')
    ON CONFLICT DO NOTHING;
    """
    print("Seeding initial water reminder...")
    result = await execute_raw_sql(seed_sql)
    print(f"Seed result: {result}")

if __name__ == "__main__":
    asyncio.run(setup_reminders_table())
