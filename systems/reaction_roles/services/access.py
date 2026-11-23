"""Política de acesso por painel: avaliação de concessões e remoções."""
def normalize_ids(values):
    ids = list(dict.fromkeys(int(x) for x in values))
    if len(ids) > 20 or any(x <= 0 for x in ids):
        raise ValueError("Informe até 20 IDs de cargos válidos.")
    return [str(x) for x in ids]

def access_policy(panel):
    raw = panel.get("access", {})
    return {"required_roles": normalize_ids(raw.get("required_roles", [])),
            "blocked_roles": normalize_ids(raw.get("blocked_roles", [])),
            "require_all": bool(raw.get("require_all", False)),
            "allowed_users": normalize_ids(raw.get("allowed_users", [])),
            "blocked_users": normalize_ids(raw.get("blocked_users", [])),
            "allow_remove": bool(raw.get("allow_remove", True))}

def can_change(panel, member, action="grant"):
    policy = access_policy(panel)
    if action == "revoke":
        return (True, "") if policy["allow_remove"] else (False, "A remoção está bloqueada neste painel.")
    uid = str(member.id)
    if uid in policy["blocked_users"]:
        return False, "Seu usuário está bloqueado neste painel."
    if policy["allowed_users"] and uid not in policy["allowed_users"]:
        return False, "Seu usuário não está autorizado neste painel."
    held = {str(r.id) for r in member.roles}
    if held.intersection(policy["blocked_roles"]):
        return False, "Você possui um cargo bloqueado neste painel."
    required = set(policy["required_roles"])
    if required and (not (required <= held) if policy["require_all"] else not bool(required & held)):
        return False, "Você não possui os cargos exigidos neste painel."
    return True, ""

async def save_access(store, guild_id, panel_id, access):
    access = access_policy({"access": access})
    if set(access["required_roles"]) & set(access["blocked_roles"]):
        raise ValueError("O mesmo cargo não pode ser obrigatório e bloqueado.")
    def mutate(data):
        panel = data.get("panels", {}).get(panel_id)
        if panel is None:
            raise ValueError("Painel não encontrado.")
        panel["access"] = access
    await store.mutate(guild_id, mutate)
