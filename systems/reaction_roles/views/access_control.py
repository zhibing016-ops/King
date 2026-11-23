"""Configuração de requisitos e restrições por modais do Discord."""
import discord
from .permissions import admin_only
from ..services.access import access_policy, save_access

def parse_ids(value):
    value = value.strip()
    if not value:
        return []
    values = [part.strip() for part in value.replace("\\n", ",").split(",")]
    if any(not x.isdecimal() for x in values):
        raise ValueError("Use apenas IDs numéricos separados por vírgulas.")
    return values

class AccessModal(discord.ui.Modal, title="KING PLUS • Restrições"):
    required = discord.ui.TextInput(label="Cargos obrigatórios (IDs)", required=False, max_length=400)
    blocked = discord.ui.TextInput(label="Cargos bloqueados (IDs)", required=False, max_length=400)
    allowed_users = discord.ui.TextInput(label="Usuários permitidos (IDs)", required=False, max_length=400)
    blocked_users = discord.ui.TextInput(label="Usuários bloqueados (IDs)", required=False, max_length=400)
    flags = discord.ui.TextInput(label="Todos obrigatórios? / Permitir remoção? (S/N)", max_length=5)

    def __init__(self, store, guild_id, owner_id, panel):
        super().__init__(timeout=300)
        self.store, self.guild_id, self.owner_id, self.panel_id = store, guild_id, owner_id, panel["id"]
        access = access_policy(panel)
        for key, field in (("required_roles", self.required), ("blocked_roles", self.blocked),
                           ("allowed_users", self.allowed_users), ("blocked_users", self.blocked_users)):
            field.default = ", ".join(access[key])
        self.flags.default = ("S" if access["require_all"] else "N") + "/" + ("S" if access["allow_remove"] else "N")

    async def on_submit(self, interaction):
        if not await admin_only(interaction, self.guild_id, self.owner_id):
            return
        try:
            flags = str(self.flags).upper().replace(" ", "").split("/")
            if len(flags) != 2 or any(f not in ("S", "N") for f in flags):
                raise ValueError("Informe S/N, S/S, N/N ou N/S nas opções.")
            access = {
                "required_roles": parse_ids(str(self.required)),
                "blocked_roles": parse_ids(str(self.blocked)),
                "allowed_users": parse_ids(str(self.allowed_users)),
                "blocked_users": parse_ids(str(self.blocked_users)),
                "require_all": flags[0] == "S",
                "allow_remove": flags[1] == "S"
            }
            await save_access(self.store, self.guild_id, self.panel_id, access)
        except ValueError as exc:
            return await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
        await interaction.response.send_message("✅ Requisitos e restrições salvos em JSON.", ephemeral=True)

class AccessActions(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panel_id):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id, self.panel_id = store, guild_id, owner_id, panel_id

    @discord.ui.button(label="Configurar restrições", emoji="🔐")
    async def configure(self, interaction, button):
        if not await admin_only(interaction, self.guild_id, self.owner_id):
            return
        panel = (await self.store.get(self.guild_id)).get("panels", {}).get(self.panel_id)
        if not panel:
            return await interaction.response.send_message("Painel removido.", ephemeral=True)
        await interaction.response.send_modal(AccessModal(self.store, self.guild_id, self.owner_id, panel))

    @discord.ui.button(label="Ver regras", emoji="📋")
    async def inspect(self, interaction, button):
        if not await admin_only(interaction, self.guild_id, self.owner_id):
            return
        panel = (await self.store.get(self.guild_id)).get("panels", {}).get(self.panel_id)
        if not panel:
            return await interaction.response.send_message("Painel removido.", ephemeral=True)
        a = access_policy(panel)
        lines = [f"**{k}:** {', '.join(map(str,v)) if isinstance(v,list) else v}" for k,v in a.items()]
        await interaction.response.send_message("\\n".join(lines), ephemeral=True)

class AccessSelect(discord.ui.Select):
    def __init__(self, panels):
        super().__init__(placeholder="Selecione um painel", options=[
            discord.SelectOption(label=p["title"][:100], value=pid) for pid,p in list(panels.items())[:25]])
    async def callback(self, interaction):
        view = self.view
        if not await admin_only(interaction, view.guild_id, view.owner_id):
            return
        await interaction.response.send_message("Regras de acesso deste painel:",
            view=AccessActions(view.store, view.guild_id, view.owner_id, self.values[0]), ephemeral=True)

class AccessManager(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panels):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id
        self.add_item(AccessSelect(panels))
