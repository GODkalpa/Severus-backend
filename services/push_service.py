import os
import json
from datetime import datetime, timezone
from pywebpush import webpush, WebPushException
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Load VAPID keys from environment
load_dotenv(".env.local")

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_CLAIMS = {
    "sub": "mailto:severus@doe.com" 
}

def send_push_notification(subscription_info: Dict[str, Any], message: str, title: str = "REVELIO_NOTIFY"):
    """
    Sends a push notification to a specific device subscription.
    """
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        print("❌ VAPID keys not configured. Cannot send push.")
        return False

    payload = {
        "title": title,
        "body": message,
        "icon": "/icons/icon-192x192.png",
        "badge": "/icons/icon-192x192.png",
        "vibrate": [200, 100, 200],
        "silent": False,
        "data": {
            "url": "/",
            "arrival_time": datetime.now(timezone.utc).isoformat()
        }
    }

    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS
        )
        print(f"✅ Push delivered to {subscription_info.get('endpoint')[:30]}...")
        return True
    except WebPushException as ex:
        print(f"❌ WebPush failed: {ex}")
        # If subscription is expired or invalid, we'd ideally remove it from DB
        return False
    except Exception as e:
        print(f"❌ Unexpected push error: {e}")
        return False

async def get_all_subscriptions():
    """
    Retrieves all active push subscriptions from Supabase.
    """
    from services.brain import supabase
    try:
        response = supabase.table("push_subscriptions").select("*").execute()
        return response.data
    except Exception as e:
        print(f"❌ Error fetching subscriptions: {e}")
        return []

async def save_subscription(subscription: Dict[str, Any]):
    """
    Saves or updates a push subscription in the database.
    """
    from services.brain import supabase
    try:
        # P256DH and Auth are stored in keys object of Web Push subscription
        data = {
            "endpoint": subscription["endpoint"],
            "p256dh": subscription["keys"]["p256dh"],
            "auth": subscription["keys"]["auth"]
        }
        
        # Upsert based on endpoint
        response = supabase.table("push_subscriptions").upsert(
            data, on_conflict="endpoint"
        ).execute()
        return response.data
    except Exception as e:
        print(f"❌ Error saving subscription: {e}")
        return None
