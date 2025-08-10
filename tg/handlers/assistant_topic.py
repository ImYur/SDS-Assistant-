
from tg.bot import bot
from core.kb_snapshot import build_snapshot
from ai.openai_http import chat
from core.utils import md2_escape
import config

def register(bot):

    def in_assistant(m): 
        return m.chat.id==config.GROUP_CHAT_ID and getattr(m,'message_thread_id',None)==config.ASSISTANT_TOPIC

    @bot.message_handler(func=lambda m: in_assistant(m), content_types=['text'])
    def assistant(m):
        kb = build_snapshot()
        q = m.text or ""
        answer = chat([
            {"role":"system","content":"You are an internal assistant. Use the provided knowledge base to answer precisely. Return 1–5 best matches with links if applicable. Be concise."},
            {"role":"user","content":f"Knowledge base:\n{kb}\n\nQuestion:\n{q}"}
        ], temperature=0.3, max_tokens=400)
        bot.reply_to(m, md2_escape(answer), parse_mode="MarkdownV2")
