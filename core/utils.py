
from datetime import datetime

def now():
    return datetime.utcnow().isoformat(timespec="seconds")

def md2_escape(s: str) -> str:
    if not s: return ""
    s = s.replace("\\","\\\\")
    for ch in ['_','*','[',']','(',')','~','`','>','#','+','-','=','|','{','}','.','!']:
        s = s.replace(ch, '\\'+ch)
    return s
