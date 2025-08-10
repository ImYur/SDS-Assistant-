
import os, requests
from config import OPENAI_API_KEY, OPENAI_BASE_URL

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
}

def chat(messages, model="gpt-4o-mini", temperature=0.7, max_tokens=350):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")
    url = f"{OPENAI_BASE_URL}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }
    r = requests.post(url, headers=HEADERS, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return (data["choices"][0]["message"]["content"] or "").strip()
