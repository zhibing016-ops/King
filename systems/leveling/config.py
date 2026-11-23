from copy import deepcopy

DEFAULT_CONFIG = {
    "enabled": False,
    "rank_theme": "dark",
    "rank_accent": None,
    "rank_background": None,
    "xp_per_message_min": 15,
    "xp_per_message_max": 25,
    "cooldown_seconds": 60,
    "level_up_channel_id": None,
    "ignored_channel_ids": [],
    "ignored_role_ids": [],
    "rewards": {},
    "reward_mode": "stack",
    "announce_level_up": True,
    "level_up_message": "🎉 Parabéns {mention}! Você alcançou o nível **{level}**!",
    "level_up_embed": True,
}

def new_config():
    return deepcopy(DEFAULT_CONFIG)
