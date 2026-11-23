"""Phase 09: configurable local anti-duplicate policy. Single-process JSON store."""
from datetime import datetime, timedelta, timezone

ACTIVE = frozenset(('pending', 'processing', 'review', 'delivered'))
DEFAULTS = {'per_discord': 1, 'per_uid': 1, 'cooldown_seconds': 30}

def policy_for(code):
    raw = code.get('limits', {})
    return {key: int(raw.get(key, value)) for key, value in DEFAULTS.items()}

def configure_limits(code, per_discord, per_uid, cooldown_seconds):
    values = (int(per_discord), int(per_uid), int(cooldown_seconds))
    if not (1 <= values[0] <= 100 and 1 <= values[1] <= 100 and 0 <= values[2] <= 86400):
        raise ValueError('Limites inválidos: Discord e UID entre 1–100; cooldown entre 0–86400 segundos.')
    code['limits'] = dict(zip(DEFAULTS, values))
    return code['limits']

def enforce_limits(data, guild_id, game_key, code, user_id, identifier):
    claims = [c for c in data.get('claims', []) if str(c.get('guild_id')) == str(guild_id)
              and c.get('game_key') == game_key and c.get('code_id') == code['id']]
    policy = policy_for(code)
    active = [c for c in claims if c.get('status') in ACTIVE]
    discord_claims = [c for c in active if str(c.get('user_id')) == str(user_id)]
    uid_claims = [c for c in active if str(c.get('identifier', '')).casefold() == str(identifier).casefold()]
    if len(discord_claims) >= policy['per_discord']:
        raise ValueError('Limite de resgates deste código por conta Discord atingido.')
    if len(uid_claims) >= policy['per_uid']:
        raise ValueError('Limite de resgates deste código por UID atingido.')
    if policy['cooldown_seconds']:
        now = datetime.now(timezone.utc)
        for claim in claims:
            if str(claim.get('user_id')) != str(user_id):
                continue
            try:
                created = datetime.fromisoformat(claim['created_at'])
                if created.tzinfo is None: created = created.replace(tzinfo=timezone.utc)
            except (KeyError, TypeError, ValueError):
                continue
            remaining = (created + timedelta(seconds=policy['cooldown_seconds']) - now).total_seconds()
            if remaining > 0:
                raise ValueError(f'Aguarde {int(remaining)+1}s antes de tentar novamente.')
