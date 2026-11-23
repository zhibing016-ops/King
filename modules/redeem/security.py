"""Per-guild delegated administrators. Manage Server is always an override."""
from modules.redeem.store import load, save

MAX_ROLES = 10

def get_roles(guild_id):
    settings = load().get('settings', {}).get(str(guild_id), {})
    return [str(x) for x in settings.get('admin_role_ids', [])]

def authorized(interaction):
    if not interaction.guild or not interaction.user:
        return False
    if interaction.user.id == interaction.guild.owner_id:
        return True
    if interaction.user.guild_permissions.manage_guild:
        return True
    role_ids = set(get_roles(interaction.guild_id))
    return bool(role_ids.intersection(str(r.id) for r in getattr(interaction.user, 'roles', [])))

def can_manage_roles(interaction):
    return bool(interaction.guild and (interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.manage_guild))

def set_roles(guild_id, role_ids):
    role_ids = list(dict.fromkeys(str(x) for x in role_ids))
    if len(role_ids) > MAX_ROLES:
        raise ValueError('Limite de 10 cargos administrativos.')
    data = load()
    data.setdefault('settings', {}).setdefault(str(guild_id), {})['admin_role_ids'] = role_ids
    save(data)
