"""Progressão cumulativa: XP total necessário para nível L = 100 * L²."""
from math import isqrt

def level_from_xp(total_xp: int) -> int:
    return isqrt(max(0, int(total_xp)) // 100)

def xp_for_level(level: int) -> int:
    return 100 * max(0, int(level)) ** 2
