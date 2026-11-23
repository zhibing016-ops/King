"""Reversed e Binding, mutuamente exclusivos com Unique/Verify."""
MODES = ("normal", "unique", "verify", "reversed", "binding")

def panel_mode(panel: dict) -> str:
    if panel.get("verify"):
        return "verify"
    if panel.get("unique"):
        return "unique"
    if panel.get("reversed"):
        return "reversed"
    if panel.get("binding"):
        return "binding"
    return "normal"

def role_action(panel: dict, adding: bool) -> str | None:
    """Retorna grant, revoke ou None para um evento de reação."""
    mode = panel_mode(panel)
    if mode == "reversed":
        return "revoke" if adding else "grant"
    if mode in ("verify", "binding") and not adding:
        return None
    return "grant" if adding else "revoke"

async def set_mode(store, guild_id: int, panel_id: str, mode: str) -> dict:
    if mode not in ("normal", "reversed", "binding"):
        raise ValueError("Modo inválido.")
    def change(data):
        panel = data.setdefault("panels", {}).get(panel_id)
        if panel is None:
            raise ValueError("Painel não encontrado.")
        if mode != "normal":
            if not panel.get("roles"):
                raise ValueError("Associe pelo menos um emoji/cargo antes de ativar o modo.")
            if panel.get("unique") or panel.get("verify") or panel.get("temporary_seconds"):
                raise ValueError("Desative Unique/Verify antes de ativar Reversed/Binding.")
        panel["reversed"] = mode == "reversed"
        panel["binding"] = mode == "binding"
    data = await store.mutate(guild_id, change)
    return data["panels"][panel_id]
