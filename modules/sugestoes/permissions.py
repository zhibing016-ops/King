"""Permissões centralizadas da equipe de sugestões."""
from modules.sugestoes.storage import read_data


def is_manager(interaction):
    return bool(interaction.guild and interaction.user.guild_permissions.manage_guild)


async def can_review(interaction):
    if is_manager(interaction):
        return True
    if not interaction.guild or not interaction.user:
        return False
    data = await read_data(interaction.guild_id)
    roles = set(data.get("settings", {}).get("review_role_ids", []))
    return any(role.id in roles for role in getattr(interaction.user, "roles", []))
