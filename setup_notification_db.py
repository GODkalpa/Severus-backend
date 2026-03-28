import asyncio
import os
from dotenv import load_dotenv
from services.brain import execute_raw_sql

load_dotenv(".env.local")

async def setup_notification_db():
    print("🪄 [REVELIO] Initializing Notification & Reminder Vault...")
    
    # 1. Create push_subscriptions table
    # This stores VAPID endpoints and keys for each device (e.g., your Samsung/iPhone)
    print("Creating 'push_subscriptions' table...")
    sql_push = """
    CREATE TABLE IF NOT EXISTS push_subscriptions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        endpoint TEXT UNIQUE NOT NULL,
        p256dh TEXT NOT NULL,
        auth TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    await execute_raw_sql(sql_push)

    # 2. Create reminders table
    # This handles the 24/7 logic (e.g., Water every 2 hours)
    print("Creating 'reminders' table...")
    sql_reminders = """
    CREATE TABLE IF NOT EXISTS reminders (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        task TEXT NOT NULL,
        interval_hours INTEGER NOT NULL,
        last_notified_at TIMESTAMPTZ DEFAULT NOW(),
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    await execute_raw_sql(sql_reminders)

    # 3. Seed initial reminder for the user
    # "Drink Water Every 2 Hours"
    print("Seeding initial 2-hour water reminder...")
    seed_sql = """
    INSERT INTO reminders (task, interval_hours) 
    VALUES ('Drink water // REVELIO_VITALS', 2)
    ON CONFLICT DO NOTHING;
    """
    await execute_raw_sql(seed_sql)

    print("✅ [REVELIO] Notification Vault ready.")

if __name__ == "__main__":
    asyncio.run(setup_notification_db())
