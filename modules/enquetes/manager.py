from datetime import datetime, timezone, timedelta
from uuid import uuid4
from .storage import read, write

def now(): return datetime.now(timezone.utc)
def active(p): return p.get("status") == "open" and (not p.get("ends_at") or now() < datetime.fromisoformat(p["ends_at"]))
async def create(guild_id, owner_id, question, options, minutes=60, **extras):
    options = [o.strip() for o in options if o.strip()]
    if not 2 <= len(options) <= 20: raise ValueError("Use de 2 a 20 opções.")
    polls = read("polls", {})
    pid = uuid4().hex[:12]
    p = dict(id=pid, guild_id=guild_id, owner_id=owner_id, question=question[:250], options=options, votes={}, status="draft", created_at=now().isoformat(), ends_at=(now()+timedelta(minutes=minutes)).isoformat(), message_id=None, channel_id=None, anonymous=False, multiple=False, max_choices=1, **extras)
    polls[pid]=p
    await write("polls",polls)
    return p
async def update(p):
    polls=read("polls",{})
    polls[p["id"]]=p
    await write("polls",polls)
async def cast(pid, user_id, choices):
    polls=read("polls",{})
    p=polls.get(pid)
    if not p or not active(p): raise ValueError("Enquete indisponível ou encerrada.")
    if not choices or len(choices)>p.get("max_choices",1) or len(set(choices))!=len(choices) or any(i<0 or i>=len(p["options"]) for i in choices): raise ValueError("Escolha inválida.")
    p["votes"][str(user_id)]=choices
    await write("polls",polls)
    return p

def counts(p):
    return [sum(i in selections for selections in p["votes"].values()) for i in range(len(p["options"]))]
