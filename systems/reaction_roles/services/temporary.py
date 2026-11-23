"""Cargos temporários: registros persistentes e expiração por UTC."""
from datetime import datetime, timezone, timedelta

MIN_SECONDS = 60
MAX_SECONDS = 30 * 86400

def validate_duration(seconds: int) -> int:
    if not isinstance(seconds, int) or not MIN_SECONDS <= seconds <= MAX_SECONDS:
        raise ValueError("A duração deve ficar entre 60 segundos e 30 dias.")
    return seconds

async def configure_temporary(store, guild_id, panel_id, seconds):
    if seconds is not None:
        validate_duration(seconds)
    def change(data):
        panel = data.setdefault('panels', {}).get(panel_id)
        if panel is None:
            raise ValueError('Painel não encontrado.')
        if seconds is not None:
            if not panel.get('roles'):
                raise ValueError('Associe um emoji e cargo primeiro.')
            if any(panel.get(m) for m in ('unique', 'verify', 'reversed', 'binding')):
                raise ValueError('Desative Unique, Verify, Reversed ou Binding antes.')
        panel['temporary_seconds'] = seconds
    data = await store.mutate(guild_id, change)
    return data['panels'][panel_id]

async def register_grant(store, guild_id, member_id, role_id, panel_id, seconds, now=None):
    validate_duration(seconds)
    now = now or datetime.now(timezone.utc)
    expires = (now + timedelta(seconds=seconds)).isoformat()
    key = f'{member_id}:{role_id}'
    def change(data):
        data.setdefault('temporary_grants', {})[key] = {
            'member_id': str(member_id), 'role_id': str(role_id),
            'panel_id': str(panel_id), 'expires_at': expires}
    await store.mutate(guild_id, change)
    return expires

async def unregister_grant(store, guild_id, member_id, role_id):
    await store.mutate(guild_id, lambda data: data.setdefault('temporary_grants', {}).pop(f'{member_id}:{role_id}', None))

def expired_grants(data, now=None):
    now = now or datetime.now(timezone.utc)
    result = []
    for key, item in data.get('temporary_grants', {}).items():
        try:
            expires = datetime.fromisoformat(item['expires_at'])
            if expires.tzinfo is not None and expires <= now:
                result.append((key, item))
        except (KeyError, ValueError, TypeError):
            continue
    return result

async def remove_if_unchanged(store, guild_id, key, expected_expiry):
    removed = False
    def change(data):
        nonlocal removed
        grants = data.setdefault('temporary_grants', {})
        if grants.get(key, {}).get('expires_at') == expected_expiry:
            grants.pop(key, None)
            removed = True
    await store.mutate(guild_id, change)
    return removed
