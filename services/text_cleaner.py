import re

def clean_spoken_text(text: str) -> str:
    """
    Cleans text for Text-to-Speech (TTS) engine.
    Strips markdown formatting, XML/HTML-style tags, code blocks, and non-verbal artifacts.
    """
    if not text:
        return ""

    # 1. Remove XML/HTML tag blocks including inner content (e.g., <minimax:toolcall>...</minimax:toolcall>, <think>...</think>)
    text = re.sub(r'<([a-zA-Z0-9_:-]+)[^>]*>[\s\S]*?</\1>', '', text)
    # Also strip any remaining stray or self-closing tags (<tag />, </tag>)
    text = re.sub(r'<[^>]+>', '', text)

    # 2. Remove code blocks ```...``` and inline code `...`
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # 3. Remove Markdown link format [label](url) -> label
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # 4. Remove Markdown headers (#, ##, ###)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)

    # 5. Remove Markdown bold/italics (*, **, _, __)
    text = text.replace("**", "").replace("*", "").replace("__", "").replace("_", "")

    # 6. Remove list markers (- , * , 1. ) at line start
    text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    # 7. Collapse multiple spaces / newlines
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def split_stream_sentences(buffer: str, min_words: int = 2) -> tuple[list[str], str]:
    """
    Splits an incoming streaming text buffer into completed sentences ready for TTS,
    returning (ready_sentences, remaining_buffer).
    """
    parts = re.split(r'(?<=[.!?])\s+|\n+', buffer)
    if len(parts) <= 1:
        return [], buffer

    ready: list[str] = []
    temp = ""
    for part in parts[:-1]:
        clean_part = part.strip()
        if not clean_part:
            continue
        temp = f"{temp} {clean_part}".strip() if temp else clean_part
        if len(temp.split()) >= min_words:
            cleaned = clean_spoken_text(temp)
            if cleaned:
                ready.append(cleaned)
            temp = ""

    remainder = f"{temp} {parts[-1]}".strip() if temp else parts[-1]
    return ready, remainder
