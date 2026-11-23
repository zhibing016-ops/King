"""Configuração central da Fase 1."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / 'data' / 'reaction_roles' / 'guilds'
SCHEMA_VERSION = 1

def default_guild_config(guild_id: int) -> dict:
    return {
        'schema_version': SCHEMA_VERSION,
        'guild_id': str(guild_id),
        'enabled': True,
        'panels': {},
        'settings': {'logs_channel_id': None},
    }
