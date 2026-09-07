import requests
import urllib.parse
def extract_forecast_description(day_data):
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
    return "unavailable"


def test_weather(location):
    try:
        encoded_location = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded_location}?format=j1"
        print(f"Fetching from: {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        current = data['current_condition'][0]
        temp_c = current['temp_C']
        description = current['weatherDesc'][0]['value']
        feels_like = current['FeelsLikeC']
        print(f"Current: {description} at {temp_c}C, feels like {feels_like}C")

        forecast_days = data.get("weather") or []
        if len(forecast_days) > 1:
            tomorrow = forecast_days[1]
            tomorrow_description = extract_forecast_description(tomorrow)
            print(
                "Tomorrow: "
                f"{tomorrow_description}, {tomorrow.get('mintempC')}C to {tomorrow.get('maxtempC')}C "
                f"(avg {tomorrow.get('avgtempC')}C)"
            )
        print(f"Success: {description} at {temp_c}°C")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_weather("Dharan, Nepal")
