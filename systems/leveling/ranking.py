"""Ranking por XP total, desempate por ID para resultados estáveis."""

def ranked_members(data: dict) -> list[tuple[int, int]]:
    members = data.get("members", {})
    entries = [(int(user_id), int(record.get("xp", 0))) for user_id, record in members.items()]
    return sorted(entries, key=lambda entry: (-entry[1], entry[0]))


def member_position(data: dict, member_id: int) -> int | None:
    for index, (user_id, _) in enumerate(ranked_members(data), 1):
        if user_id == member_id:
            return index
    return None
