# ai.py
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def chat(messages, model="gpt-4o-mini", temperature=0.7, max_tokens=350):
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()

def gen_pitch(profile, job_text, system_map):
    system = system_map.get(profile, system_map["Yurii"])
    messages = [
        {"role": "system", "content": system + "\nYou are writing a short Upwork cover letter."},
        {"role": "user", "content": f"Job post:\n{job_text}\n\nWrite a concise, tailored cover letter in English. 120–180 words. End with 2 short questions."}
    ]
    return chat(messages)

def gen_reply(profile, history_messages, system_map):
    system = system_map.get(profile, system_map["Yurii"])
    messages = [{"role":"system", "content": system}]
    messages.extend(history_messages[-12:])  # тримаємо останні 12 ходів
    messages.append({"role":"user", "content": "Draft a concise, helpful reply to the last client message in English."})
    return chat(messages, max_tokens=350)

def gen_thanks(profile, brief_context, system_map):
    system = system_map.get(profile, system_map["Yurii"])
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Context:\n{brief_context}\n\nWrite a short thank-you & wrap-up note in English (3-5 sentences)."}
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
