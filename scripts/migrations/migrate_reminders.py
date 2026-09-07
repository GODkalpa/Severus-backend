import asyncio
from services.brain import execute_raw_sql

async def migrate():
    # 1. Rename last_reminded_at to last_notified_at if it exists
    # 2. Add due_at and is_one_off columns
    
    sql = """
    DO $$ 
    BEGIN
        -- Rename last_reminded_at if it exists
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='reminders' AND column_name='last_reminded_at') THEN
            ALTER TABLE public.reminders RENAME COLUMN last_reminded_at TO last_notified_at;
        END IF;

        -- Add last_notified_at if it doesn't exist (e.g. if table was empty/different)
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='reminders' AND column_name='last_notified_at') THEN
            ALTER TABLE public.reminders ADD COLUMN last_notified_at TIMESTAMPTZ DEFAULT now();
        END IF;

        -- Add due_at
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='reminders' AND column_name='due_at') THEN
            ALTER TABLE public.reminders ADD COLUMN due_at TIMESTAMPTZ;
        END IF;

        -- Add is_one_off
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='reminders' AND column_name='is_one_off') THEN
            ALTER TABLE public.reminders ADD COLUMN is_one_off BOOLEAN DEFAULT false;
        END IF;
        
        -- Make interval_hours optional (NOT NULL removed or defaulted)
        ALTER TABLE public.reminders ALTER COLUMN interval_hours DROP NOT NULL;
        ALTER TABLE public.reminders ALTER COLUMN interval_hours SET DEFAULT 2.0;

    END $$;
    """
    print("Migrating reminders table...")
    result = await execute_raw_sql(sql)
    print(f"Migration result: {result}")

if __name__ == "__main__":
    asyncio.run(migrate())
