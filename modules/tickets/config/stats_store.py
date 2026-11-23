"""Ticket statistics and feedback in JSON; single bot process only."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "data" / "ticket_stats.json"
LOCK = asyncio.Lock()

def _read():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}

def _write(data):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(PATH)

async def record_event(guild_id, channel_id, owner_id, action, actor_id=None, assignee_id=None):
    if action not in ("opened", "closed", "reopened", "deleted"):
        raise ValueError("Ação inválida")
    async with LOCK:
        data = _read()
        guild = data.setdefault(str(guild_id), {})
        ticket = guild.setdefault(str(channel_id), {
            "owner_id": owner_id, "events": [], "rating": None, "assignee_id": None
        })
        ticket["assignee_id"] = assignee_id if assignee_id is not None else ticket.get("assignee_id")
        ticket["events"].append({
            "action": action, "actor_id": actor_id,
            "at": datetime.now(timezone.utc).isoformat()
        })
        _write(data)

async def record_assignee(guild_id, channel_id, staff_id):
    async with LOCK:
        data = _read()
        ticket = data.get(str(guild_id), {}).get(str(channel_id))
        if ticket:
            ticket["assignee_id"] = staff_id
            _write(data)

async def submit_rating(guild_id, channel_id, owner_id, score):
    if not 1 <= score <= 5:
        raise ValueError("Avaliação deve ser de 1 a 5")
    async with LOCK:
        data = _read()
        ticket = data.get(str(guild_id), {}).get(str(channel_id))
        if not ticket or int(ticket["owner_id"]) != int(owner_id):
            raise ValueError("Apenas o dono pode avaliar um ticket registrado nas estatísticas")
        if ticket.get("rating") is not None:
            raise ValueError("Este ticket já foi avaliado")
        if not ticket["events"] or ticket["events"][-1]["action"] not in ("closed", "deleted"):
            raise ValueError("O ticket precisa estar fechado para avaliação")
        ticket["rating"] = score
        _write(data)

async def get_report(guild_id):
    async with LOCK:
        tickets = list(_read().get(str(guild_id), {}).values())
    totals = {name: 0 for name in ("opened", "closed", "reopened", "deleted")}
    by_staff = {}
    ratings = []
    for ticket in tickets:
        for event in ticket.get("events", []):
            action = event.get("action")
            if action in totals:
                totals[action] += 1
                if action == "closed" and event.get("actor_id"):
                    staff = str(event["actor_id"])
                    by_staff[staff] = by_staff.get(staff, 0) + 1
        if ticket.get("rating") is not None:
            ratings.append(ticket["rating"])
    return totals, by_staff, ratings
