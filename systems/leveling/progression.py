"""Consultas de progresso baseadas no XP total persistido."""
from .level_calculator import level_from_xp, xp_for_level


def progress_from_xp(total_xp: int) -> dict:
    if not isinstance(total_xp, int) or isinstance(total_xp, bool) or total_xp < 0:
        raise ValueError("XP deve ser um inteiro não negativo")
    level = level_from_xp(total_xp)
    start = xp_for_level(level)
    target = xp_for_level(level + 1)
    gained = total_xp - start
    required = target - start
    return {
        "xp": total_xp, "level": level,
        "level_start_xp": start, "next_level_xp": target,
        "current_level_xp": gained, "level_span_xp": required,
        "remaining_xp": target - total_xp,
        "percent": round(gained * 100 / required, 2),
    }


def progress_bar(current: int, required: int, width: int = 12) -> str:
    if required <= 0 or not 1 <= width <= 40:
        raise ValueError("Parâmetros inválidos")
    filled = min(width, max(0, current * width // required))
    return "▰" * filled + "▱" * (width - filled)
