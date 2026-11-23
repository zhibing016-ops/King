import re
from datetime import datetime, timezone
from uuid import uuid4

CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")

def normalize_code(value):
    value = value.strip().upper()
    if not CODE_PATTERN.fullmatch(value):
        raise ValueError("Código: 3 a 64 caracteres (A-Z, 0-9, _ ou -).")
    return value

def parse_expiry(value):
    value = value.strip()
    if not value:
        return None
    try:
        expiry = datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError("Validade deve ser AAAA-MM-DD HH:MM (UTC).")
    if expiry <= datetime.now(timezone.utc):
        raise ValueError("A validade precisa ser futura.")
    return expiry.isoformat()

def parse_limit(value):
    try:
        number = int(value.strip())
    except ValueError:
        raise ValueError("Limite deve ser um número inteiro.")
    if not 1 <= number <= 1000000:
        raise ValueError("Limite deve estar entre 1 e 1000000.")
    return number

def create_code(data, guild_id, game_key, code, reward, expiry, limit):
    normalized = normalize_code(code)
    if not reward.strip() or len(reward) > 500:
        raise ValueError("Informe uma descrição de recompensa de até 500 caracteres.")
    for existing in data.setdefault("codes", {}).values():
        if str(existing.get("guild_id")) == str(guild_id) and existing.get("game_key") == game_key and existing.get("code") == normalized:
            raise ValueError("Este código já existe para o jogo.")
    code_id = uuid4().hex
    record = {"id": code_id, "guild_id": guild_id, "game_key": game_key,
              "code": normalized, "reward": reward.strip(), "expires_at": parse_expiry(expiry),
              "max_claims": parse_limit(limit), "claims_count": 0, "enabled": True,
              "created_at": datetime.now(timezone.utc).isoformat()}
    data["codes"][code_id] = record
    return record

def guild_codes(data, guild_id, game_key=None):
    return {k:v for k,v in data.get("codes", {}).items() if str(v.get("guild_id")) == str(guild_id) and (game_key is None or v.get("game_key") == game_key)}

def code_status(record):
    if not record.get("enabled", True): return "Desativado"
    if record.get("claims_count", 0) >= record.get("max_claims", 1): return "Esgotado"
    stock = int(record.get("availability", {}).get("stock", 0))
    if stock and int(record.get("claims_count", 0)) >= stock: return "Estoque esgotado"
    expiry = record.get("expires_at")
    if expiry and datetime.fromisoformat(expiry) <= datetime.now(timezone.utc): return "Expirado"
    return "Disponível (Claim ainda indisponível)"
