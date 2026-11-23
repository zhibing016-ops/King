"""Associações emoji → cargo; a atribuição efetiva começa na Fase 5."""
import re

MAX_ROLES_PER_PANEL = 20
CUSTOM_EMOJI = re.compile(r"^<a?:[A-Za-z0-9_]{2,32}:[0-9]{15,22}>$")

def validate_emoji(emoji: str) -> str:
    emoji = emoji.strip()
    if not emoji or len(emoji) > 64 or any(c.isspace() for c in emoji):
        raise ValueError('Informe um emoji Unicode ou personalizado válido.')
    if emoji.startswith('<') and not CUSTOM_EMOJI.fullmatch(emoji):
        raise ValueError('Formato de emoji personalizado inválido.')
    if emoji.isascii() and not CUSTOM_EMOJI.fullmatch(emoji):
        raise ValueError('Use um emoji, não texto comum.')
    return emoji

async def add_mapping(store, guild_id: int, panel_id: str, emoji: str, role_id: int):
    emoji = validate_emoji(emoji)
    if role_id <= 0:
        raise ValueError('Cargo inválido.')
    def apply(data):
        panel = data.get('panels', {}).get(panel_id)
        if panel is None:
            raise ValueError('Painel não encontrado.')
        roles = panel.setdefault('roles', {})
        if emoji not in roles and len(roles) >= MAX_ROLES_PER_PANEL:
            raise ValueError('Limite de 20 emojis por painel.')
        roles[emoji] = str(role_id)
    await store.mutate(guild_id, apply)

async def remove_mapping(store, guild_id: int, panel_id: str, emoji: str):
    def apply(data):
        panel = data.get('panels', {}).get(panel_id)
        if panel is None or emoji not in panel.get('roles', {}):
            raise ValueError('Associação não encontrada.')
        del panel['roles'][emoji]
    await store.mutate(guild_id, apply)
