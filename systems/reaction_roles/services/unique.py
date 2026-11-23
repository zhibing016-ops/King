"""Modo Unique: no máximo um cargo do mesmo painel por membro."""

def is_unique(panel: dict) -> bool:
    return bool(panel.get("unique", False))

def conflicting_role_ids(panel: dict, selected_role_id: int) -> set[int]:
    if not is_unique(panel):
        return set()
    return {int(value) for value in panel.get("roles", {}).values() if int(value) != selected_role_id}

async def set_unique(store, guild_id: int, panel_id: str, enabled: bool) -> dict:
    def change(data):
        panel = data.setdefault("panels", {}).get(panel_id)
        if panel is None:
            raise ValueError("Painel não encontrado.")
        if enabled and (panel.get("verify") or panel.get("reversed") or panel.get("binding")):
            raise ValueError("Desative Verify, Reversed ou Binding antes de ativar Unique.")
        panel["unique"] = bool(enabled)
    data = await store.mutate(guild_id, change)
    return data["panels"][panel_id]
