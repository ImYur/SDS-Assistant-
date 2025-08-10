# ai.py — HTTP-виклики до OpenAI Chat Completions без SDK
import os
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
}

def chat(messages, model="gpt-4o-mini", temperature=0.7, max_tokens=350):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")
    url = f"{OPENAI_BASE}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }
    resp = requests.post(url, headers=HEADERS, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return (data["choices"][0]["message"]["content"] or "").strip()

def gen_pitch(profile, job_text, system_map):
    system = system_map.get(profile, system_map["Yurii"])
    messages = [
        {"role": "system", "content": system + "\nYou are writing a short Upwork cover letter."},
        {"role": "user", "content": (
            "Job post:\n"
            f"{job_text}\n\n"
            "Write a concise, tailored cover letter in English (120–180 words). "
            "Close with 2 brief, relevant questions."
        )}
    ]
    return chat(messages, temperature=0.7, max_tokens=350)

def gen_reply(profile, history_messages, system_map):
    system = system_map.get(profile, system_map["Yurii"])
    messages = [{"role":"system", "content": system}]
    messages.extend(history_messages[-12:])
    messages.append({"role":"user", "content":"Draft a concise, helpful reply to the last client message in English."})
    return chat(messages, temperature=0.7, max_tokens=350)

def gen_thanks(profile, brief_context, system_map):
    system = system_map.get(profile, system_map["Yurii"])
    messages = [
        {"role":"system", "content": system},
        {"role":"user", "content": f"Context:\n{brief_context}\n\nWrite a short thank-you & wrap-up note in English (3–5 sentences)."}
    ]
    return chat(messages, temperature=0.6, max_tokens=220)

def assistant_answer(kb_text, question):
    messages = [
        {"role":"system", "content":
         "You are an internal assistant. Use the provided knowledge base to answer precisely. "
         "Return 1–5 best matches with links if applicable. Be concise."},
        {"role":"user", "content": f"Knowledge base:\n{kb_text}\n\nQuestion:\n{question}"}
    ]
    return chat(messages, temperature=0.3, max_tokens=400)
