import os
import re
import html
import asyncio
import urllib.parse
import requests
import aiohttp
from datetime import datetime, timezone, timedelta

SEARCH_TIMEOUT_SECONDS = int(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "10"))
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
WEB_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

def _get_current_time_nepal():
    nepal_offset = timezone(timedelta(hours=5, minutes=45))
    return datetime.now(nepal_offset)

def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())

def _strip_html_tags(raw_html: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style|noscript|svg).*?>.*?</\1>", " ", raw_html or "")
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    return _normalize_text(html.unescape(cleaned))

def _clip_text(value: str, limit: int) -> str:
    value = _normalize_text(value)
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."

def _extract_duckduckgo_results(raw_html: str, max_results: int) -> list[dict]:
    matches = re.findall(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        raw_html or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    results = []
    seen_urls = set()

    for href, title_html in matches:
        parsed = urllib.parse.urlparse(html.unescape(href))
        redirect_target = urllib.parse.parse_qs(parsed.query).get("uddg", [None])[0]
        url = urllib.parse.unquote(redirect_target) if redirect_target else html.unescape(href)

        if not url.startswith("http") or url in seen_urls:
            continue

        results.append({
            "title": _strip_html_tags(title_html) or url,
            "url": url,
            "snippet": "",
        })
        seen_urls.add(url)

        if len(results) >= max_results:
            break

    return results

async def _fetch_page_excerpt(url: str, char_limit: int = 1800) -> str:
    timeout = aiohttp.ClientTimeout(total=4.0, connect=2.0)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {"User-Agent": WEB_USER_AGENT}
            async with session.get(url, headers=headers, ssl=False) as response:
                if response.status != 200:
                    return f"Status {response.status}"
                
                content_type = (response.headers.get("content-type") or "").lower()
                if "html" not in content_type and "text" not in content_type:
                    return f"Skipped non-HTML ({content_type or 'unknown'})."
                
                html_text = await response.text()
                text = _strip_html_tags(html_text)
                return _clip_text(text, char_limit) if text else "No readable text extracted."
    except asyncio.TimeoutError:
        return "Connection timed out."
    except Exception as exc:
        return f"Fetch error: {str(exc)}"

async def _search_with_tavily(query: str, max_results: int) -> list[dict]:
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
    }
    response = await asyncio.to_thread(
        requests.post,
        "https://api.tavily.com/search",
        json=payload,
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    return [
        {
            "title": item.get("title") or item.get("url") or "Untitled result",
            "url": item.get("url") or "",
            "snippet": item.get("content") or "",
        }
        for item in data.get("results", [])
        if item.get("url")
    ][:max_results]

async def _search_with_serper(query: str, max_results: int) -> list[dict]:
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"q": query, "num": max_results}
    response = await asyncio.to_thread(
        requests.post,
        "https://google.serper.dev/search",
        headers=headers,
        json=payload,
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    return [
        {
            "title": item.get("title") or item.get("link") or "Untitled result",
            "url": item.get("link") or "",
            "snippet": item.get("snippet") or "",
        }
        for item in data.get("organic", [])
        if item.get("link")
    ][:max_results]

async def _search_with_duckduckgo(query: str, max_results: int) -> list[dict]:
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    response = await asyncio.to_thread(
        requests.get,
        search_url,
        headers={"User-Agent": WEB_USER_AGENT},
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _extract_duckduckgo_results(response.text, max_results)

async def search_the_web(query: str, max_results: int = 5) -> str:
    """
    Searches the public web for current information and returns source-backed notes.
    """
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return "Please provide a query to search."

    max_results = max(1, min(int(max_results or 5), 5))
    provider_name = "duckduckgo"
    fallback_reason = None
    print(f"[TOOL] Searching the web for: {normalized_query}...")

    results = []
    if TAVILY_API_KEY:
        try:
            provider_name = "tavily"
            results = await _search_with_tavily(normalized_query, max_results)
            if not results:
                fallback_reason = "Tavily returned no results."
        except Exception as exc:
            fallback_reason = f"Tavily unavailable: {exc}"
            results = []
    elif SERPER_API_KEY:
        try:
            provider_name = "serper"
            results = await _search_with_serper(normalized_query, max_results)
            if not results:
                fallback_reason = "Serper returned no results."
        except Exception as exc:
            fallback_reason = f"Serper unavailable: {exc}"
            results = []

    if not results:
        try:
            provider_name = "duckduckgo"
            results = await _search_with_duckduckgo(normalized_query, max_results)
        except Exception as exc:
            return f"Web search could not be completed: {exc}"

    if not results:
        return f"No results found for '{normalized_query}'."

    excerpts = await asyncio.gather(
        *[_fetch_page_excerpt(result["url"]) for result in results],
        return_exceptions=True,
    )

    timestamp = _get_current_time_nepal().strftime("%Y-%m-%d %H:%M %Z")
    lines = [
        f"Web search results for '{normalized_query}' ({provider_name}, {timestamp}):"
    ]
    if fallback_reason and provider_name == "duckduckgo":
        lines.append(f"(Fallback note: {fallback_reason})")

    for index, (result, excerpt) in enumerate(zip(results, excerpts), start=1):
        page_excerpt = excerpt if isinstance(excerpt, str) else f"Snippet only"
        snippet = _clip_text(result.get("snippet", ""), 250) or "No snippet"
        lines.extend([
            f"{index}. {result.get('title') or 'Untitled'} - {result.get('url')}",
            f"   Summary: {snippet}",
            f"   Context: {_clip_text(page_excerpt, 600)}",
        ])

    return "\n".join(lines)
