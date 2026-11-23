"""Controle de envio atômico por servidor, persistido em JSON."""
import time
from modules.sugestoes.storage import mutate

DEFAULTS = {"enabled": True, "cooldown_seconds": 60, "daily_limit": 5, "duplicate_window_seconds": 86400}


def normalized(text):
    return " ".join(text.casefold().split())


async def reserve_submission(guild_id, user_id, text, anonymous, image_url):
    now = int(time.time())
    uid = str(user_id)

    def operation(data):
        settings = data.setdefault("settings", {})
        if anonymous and not settings.get("anonymous_enabled", False):
            return None, "Sugestões anônimas estão desativadas."
        rules = {**DEFAULTS, **settings.get("antispam", {})}
        blocked = {int(v) for v in settings.get("suggestion_blocked_ids", [])}
        if user_id in blocked:
            return None, "Você está bloqueado de enviar sugestões neste servidor."
        if rules["enabled"]:
            # Apenas envios bem-sucedidos e reservas pendentes contam no limite.
            history = [r for r in data.get("suggestions", {}).values()
                       if r.get("author_id") == user_id and r.get("status") != "Falha no envio"]
            recent = [r for r in history if now - int(r.get("created_at", 0)) < 86400]
            if rules["daily_limit"] and len(recent) >= rules["daily_limit"]:
                return None, "Você atingiu o limite de sugestões das últimas 24 horas."
            if history and rules["cooldown_seconds"]:
                last = max(int(r.get("created_at", 0)) for r in history)
                remaining = rules["cooldown_seconds"] - (now - last)
                if remaining > 0:
                    return None, f"Aguarde {remaining} segundo(s) para enviar outra sugestão."
            window = rules["duplicate_window_seconds"]
            if window and any(normalized(r.get("text", "")) == normalized(text)
                              and now - int(r.get("created_at", 0)) < window for r in history):
                return None, "Você já enviou uma sugestão igual recentemente."
        number = data.setdefault("next_id", 1)
        data["next_id"] = number + 1
        data.setdefault("suggestions", {})[str(number)] = {
            "author_id": user_id, "anonymous": anonymous, "image_url": image_url,
            "text": text, "status": "Pendente", "message_id": None,
            "created_at": now,
        }
        return number, None

    return await mutate(guild_id, operation)
