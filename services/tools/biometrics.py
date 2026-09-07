from datetime import datetime, timezone, timedelta
from services.db import supabase

def _get_current_time_nepal():
    nepal_offset = timezone(timedelta(hours=5, minutes=45))
    return datetime.now(nepal_offset)

async def log_biometric(metric_type: str, value: float, unit: str = "", notes: str = "") -> str:
    """
    Logs physical health data (weight, water intake, sleep, steps) to biometrics table.
    """
    if not supabase:
        return "Biometric health system is currently offline."

    try:
        data = {
            "metric_type": metric_type.strip().lower(),
            "value": float(value),
            "unit": unit.strip(),
            "notes": notes.strip(),
            "logged_at": _get_current_time_nepal().isoformat()
        }
        supabase.table("biometrics").insert(data).execute()
        return f"Logged {value} {unit} for {metric_type}."
    except Exception as e:
        print(f"Error logging biometric: {e}")
        return f"Error updating health records: {str(e)}"


async def log_calories(food_name: str, calories: int) -> str:
    """
    Convenience tool to log calories into biometrics.
    """
    return await log_biometric(metric_type="calories", value=float(calories), unit="kcal", notes=food_name)


async def get_daily_biometrics() -> str:
    """
    Fetches and summarizes all health entries from biometrics table for today.
    """
    if not supabase:
        return "Health telemetry is currently offline."

    try:
        today = _get_current_time_nepal().date().isoformat()
        response = (
            supabase.table("biometrics")
            .select("metric_type, value, unit")
            .gte("logged_at", today)
            .execute()
        )

        records = response.data or []
        if not records:
            return "No health metrics have been recorded for today."

        summary_data: dict[str, dict] = {}
        for r in records:
            m_type = r["metric_type"]
            val = float(r.get("value", 0))
            unit = r.get("unit", "")
            if m_type not in summary_data:
                summary_data[m_type] = {"total": 0.0, "unit": unit}
            summary_data[m_type]["total"] += val

        lines = ["Today's health metrics:"]
        for m_type, data in summary_data.items():
            lines.append(f"- Total {m_type}: {data['total']} {data['unit']}".strip())

        return "\n".join(lines)
    except Exception as e:
        print(f"Error fetching daily biometrics: {e}")
        return f"Error retrieving health telemetry: {str(e)}"
