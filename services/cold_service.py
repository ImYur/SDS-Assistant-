
from core import repo_cold
from ai import openai_http
from ai import prompts

SYSTEM_MAP = {"Yurii": prompts.YURII_SYSTEM, "Olena": prompts.OLENA_SYSTEM}

def gen_pitch(profile, job_text):
    system = SYSTEM_MAP.get(profile, prompts.YURII_SYSTEM)
    messages = [
        {"role":"system", "content": system + "\nYou are writing a short Upwork cover letter."},
        {"role":"user", "content": f"Job post:\n{job_text}\n\nWrite a concise, tailored cover letter in English (120–180 words). Close with 2 brief, relevant questions."}
    ]
    return openai_http.chat(messages, temperature=0.7, max_tokens=350)

def capture_lead(message_id, text):
    repo_cold.add(message_id, text)

def set_profile(message_id, profile):
    repo_cold.set_profile(message_id, profile)

def save_pitch(message_id, pitch_text):
    repo_cold.set_pitch(message_id, pitch_text)

def get_text(message_id):
    return repo_cold.get_text(message_id)

def get_pitch(message_id):
    return repo_cold.get_pitch(message_id)

def kb_snapshot(limit=200):
    return repo_cold.snapshot(limit=limit)
