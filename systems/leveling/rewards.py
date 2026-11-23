"""Recompensas por nível, com suporte a modos cumulativo e substituição."""
from .level_calculator import level_from_xp

def normalized_rewards(config):
    rewards = config.get("rewards", {})
    if not isinstance(rewards, dict):
        raise ValueError("Configuração de recompensas inválida")
    result = {}
    for key, value in rewards.items():
        level, role_id = int(key), int(value)
        if level < 1 or role_id <= 0:
            raise ValueError("Recompensa inválida")
        result[level] = role_id
    return result

def desired_roles(config, level):
    eligible = sorted((lvl, role) for lvl, role in normalized_rewards(config).items() if lvl <= level)
    if config.get("reward_mode", "stack") == "replace":
        return {eligible[-1][1]} if eligible else set()
    return {role for _, role in eligible}

def reward_changes(config, xp, member_role_ids):
    """Retorna (adicionar, remover); não altera cargos externos ao sistema."""
    all_rewards = set(normalized_rewards(config).values())
    desired = desired_roles(config, level_from_xp(xp))
    current = set(member_role_ids)
    return desired - current, (all_rewards & current) - desired
