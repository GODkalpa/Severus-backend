import urllib.parse
import asyncio
import requests
from datetime import datetime

def _extract_forecast_description(day_data):
    hourly_entries = day_data.get("hourly") or []
    preferred_entry = None

    for entry in hourly_entries:
        if entry.get("time") == "1200":
            preferred_entry = entry
            break

    if preferred_entry is None and hourly_entries:
        preferred_entry = hourly_entries[len(hourly_entries) // 2]

    if preferred_entry:
        descriptions = preferred_entry.get("weatherDesc") or []
        if descriptions and isinstance(descriptions[0], dict):
            return descriptions[0].get("value")

    return None


def _select_forecast_day(weather_days, when):
    normalized_when = (when or "current").strip().lower()
    if normalized_when in {"", "current", "now", "right now", "currently"}:
        return "current", None, "current"

    if normalized_when in {"today", "tonight", "this evening"}:
        day_index = 0
        label = "today"
    elif normalized_when == "tomorrow":
        day_index = 1
        label = "tomorrow"
    elif normalized_when in {"day after tomorrow", "overmorrow"}:
        day_index = 2
        label = "the day after tomorrow"
    else:
        try:
            requested_date = datetime.strptime(normalized_when, "%Y-%m-%d").date()
        except ValueError:
            requested_date = None

        if requested_date is not None:
            for day_data in weather_days:
                if day_data.get("date") == requested_date.isoformat():
                    return "forecast", day_data, requested_date.isoformat()
            return None, None, (
                f"I can provide the current weather plus the next {len(weather_days)} forecast days for {when}."
            )

        cleaned_when = normalized_when.replace("next ", "").replace("this ", "").strip()
        weekday_map = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        if cleaned_when in weekday_map:
            requested_weekday = weekday_map[cleaned_when]
            for day_data in weather_days:
                day_value = day_data.get("date")
                if not day_value:
                    continue
                try:
                    day_date = datetime.strptime(day_value, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if day_date.weekday() == requested_weekday:
                    return "forecast", day_data, day_date.strftime("%A")

        return None, None, (
            "I can provide the current weather, today's forecast, tomorrow's forecast, "
            "the day after tomorrow, weekday names, or a YYYY-MM-DD date."
        )

    if len(weather_days) <= day_index:
        return None, None, (
            f"I can provide the current weather plus the next {len(weather_days)} forecast days."
        )

    return "forecast", weather_days[day_index], label


async def fetch_weather(location: str, when: str = "current") -> str:
    """
    Fetches current weather or short-range forecast data using the wttr.in JSON endpoint.
    """
    try:
        encoded_location = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded_location}?format=j1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        }
        print(f"[TOOL] Fetching weather for {location} ({when})...")
        response = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)

        if response.status_code != 200:
            return f"I apologize, but the weather service returned an error (status {response.status_code})."

        data = response.json()
        if "current_condition" not in data or not data["current_condition"]:
            return "I am unable to parse meteorological data for that location."

        current = data["current_condition"][0]
        weather_days = data.get("weather") or []
        request_type, selected_day, label = _select_forecast_day(weather_days, when)

        if request_type is None:
            return label

        if request_type == "forecast":
            forecast_description = _extract_forecast_description(selected_day) or "unavailable"
            min_temp = selected_day.get("mintempC", "unknown")
            max_temp = selected_day.get("maxtempC", "unknown")
            avg_temp = selected_day.get("avgtempC", "unknown")

            forecast_label = label if label in {"today", "tomorrow", "the day after tomorrow"} else f"for {label}"
            return (
                f"The forecast {forecast_label} in {location} is {forecast_description}, "
                f"with temperatures from {min_temp}°C to {max_temp}°C (average {avg_temp}°C)."
            )

        temp_c = current.get("temp_C", "unknown")
        description = current.get("weatherDesc", [{}])[0].get("value", "Clear")
        feels_like = current.get("FeelsLikeC", temp_c)

        return f"The weather in {location} is currently {description} at {temp_c}°C, feeling like {feels_like}°C."

    except requests.exceptions.Timeout:
        return "The weather service timed out. Please try again shortly."
    except Exception as e:
        print(f"Error fetching weather: {e}")
        return f"Unable to retrieve meteorological data: {str(e)}"
