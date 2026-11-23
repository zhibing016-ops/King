"""Paginação e formatação de leaderboard (sem dependência do Discord)."""
from .ranking import ranked_members, member_position

PAGE_SIZE = 10

def leaderboard_page(data: dict, page: int = 1, page_size: int = PAGE_SIZE):
    if page_size < 1 or page_size > 25:
        raise ValueError("page_size deve estar entre 1 e 25")
    ranked = ranked_members(data)
    total_pages = max(1, (len(ranked) + page_size - 1) // page_size)
    page = max(1, min(int(page), total_pages))
    start = (page - 1) * page_size
    rows = [(index, uid, xp) for index, (uid, xp) in enumerate(ranked[start:start + page_size], start + 1)]
    return {"page": page, "pages": total_pages, "total": len(ranked), "rows": rows}


def position_summary(data: dict, member_id: int):
    position = member_position(data, member_id)
    record = data.get("members", {}).get(str(member_id))
    return {"position": position, "xp": int(record.get("xp", 0)) if record else 0,
            "total": len(data.get("members", {}))}
