import os
import json
from datetime import datetime, timezone
from pywebpush import webpush, WebPushException
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Load VAPID keys from environment
load_dotenv(".env.local")

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_CLAIMS = {
    "sub": "mailto:severus@doe.com" 
}

def send_push_notification(subscription_info: Dict[str, Any], message: str, title: str = "REVELIO_NOTIFY", url: str = "/") -> bool:
    """
    Sends a rich push notification to a specific device subscription.
    """
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        print("❌ VAPID keys not configured. Cannot send push.")
        return False

    payload = {
        "title": title,
        "body": message,
        "icon": "/icons/icon-192x192.png",
        "badge": "/icons/badge-72x72.png",
        "vibrate": [150, 80, 150, 80, 300],
        "silent": False,
        "tag": "severus-tactical-alert",
        "data": {
            "url": url,
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
        print(f"✅ Push delivered to {subscription_info.get('endpoint', '')[:35]}...")
        return True
    except WebPushException as ex:
        print(f"❌ WebPush failed: {ex}")
        # Auto-prune expired / unregistered endpoints (404 / 410 Gone)
        if hasattr(ex, "response") and ex.response is not None and getattr(ex.response, "status_code", None) in [404, 410]:
            endpoint = subscription_info.get("endpoint")
            if endpoint:
                try:
                    from services.db import supabase
                    supabase.table("push_subscriptions").delete().eq("endpoint", endpoint).execute()
                    print(f"🗑️ Pruned stale subscription: {endpoint[:35]}...")
                except Exception as del_err:
                    print(f"Failed to prune stale subscription: {del_err}")
        return False
    except Exception as e:
        print(f"❌ Unexpected push error: {e}")
        return False

async def get_all_subscriptions() -> List[Dict[str, Any]]:
    """
    Retrieves all active push subscriptions from Supabase.
    """
    from services.db import supabase
    try:
        response = supabase.table("push_subscriptions").select("*").execute()
        return response.data or []
    except Exception as e:
        print(f"❌ Error fetching subscriptions: {e}")
        return []

async def save_subscription(subscription: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Saves or updates a push subscription in the database.
    """
    from services.db import supabase
    try:
        endpoint = subscription.get("endpoint")
        keys = subscription.get("keys", {})
        if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
            print("❌ Invalid subscription payload received.")
            return None

        data = {
            "endpoint": endpoint,
            "p256dh": keys["p256dh"],
            "auth": keys["auth"]
        }
        
        # Upsert based on endpoint
        response = supabase.table("push_subscriptions").upsert(
            data, on_conflict="endpoint"
        ).execute()
        return response.data
    except Exception as e:
        print(f"❌ Error saving subscription: {e}")
        return None

async def broadcast_push_notification(message: str, title: str = "REVELIO_NOTIFY", url: str = "/") -> int:
    """
    Dispatches a push notification to all registered active devices.
    Returns the count of successfully delivered notifications.
    """
    subscriptions = await get_all_subscriptions()
    if not subscriptions:
        return 0

    success_count = 0
    for sub in subscriptions:
        sub_info = {
            "endpoint": sub["endpoint"],
            "keys": {
                "p256dh": sub["p256dh"],
                "auth": sub["auth"]
            }
        }
        delivered = send_push_notification(sub_info, message, title, url)
        if delivered:
            success_count += 1

    return success_count
