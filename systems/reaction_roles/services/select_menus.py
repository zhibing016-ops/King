"""Menus persistentes de autoatribuição; 25 opções no máximo por menu."""
import discord
from .reactions import get_member_lock
from .temporary import register_grant, unregister_grant
from .access import can_change
from .audit import record_audit

def selection_options(panel):
    # Phase 4 caps panels at 20 mappings; Discord allows up to 25.
    return [(str(emoji), int(role_id)) for emoji, role_id in list(panel.get("roles", {}).items())[:25]]

def build_select_view(bot, store, guild_id, panel):
    return RoleSelectView(bot, store, guild_id, panel)

class RoleSelect(discord.ui.Select):
    def __init__(self, panel):
        entries = selection_options(panel)
        opts = []
        for emoji, role_id in entries:
            option = discord.SelectOption(label=f"Cargo {len(opts)+1} · {role_id}", value=str(role_id))
            try:
                option.emoji = discord.PartialEmoji.from_str(emoji)
            except (TypeError, ValueError):
                pass
            opts.append(option)
        super().__init__(
            placeholder="Escolha seus cargos",
            min_values=1 if panel.get("unique") else 0,
            max_values=1 if panel.get("unique") else len(opts),
            options=opts,
            custom_id=f"kingplus:rr:select:{panel['id']}"
        )

    async def callback(self, interaction):
        await self.view.apply(interaction, {int(x) for x in self.values})

class RoleSelectView(discord.ui.View):
    def __init__(self, bot, store, guild_id, panel):
        super().__init__(timeout=None)
        self.bot, self.store, self.guild_id, self.panel_id = bot, store, guild_id, panel["id"]
        if not selection_options(panel):
            raise ValueError("O painel não possui cargos associados.")
        self.add_item(RoleSelect(panel))

    async def apply(self, interaction, selected):
        if interaction.guild_id != self.guild_id or interaction.guild is None:
            return await interaction.response.send_message("Servidor inválido.", ephemeral=True)
        data = await self.store.get(self.guild_id)
        panel = data.get("panels", {}).get(self.panel_id)
        if (not data.get("enabled") or not panel or panel.get("interface") != "select"
                or str(panel.get("message_id")) != str(interaction.message.id)
                or str(panel.get("channel_id")) != str(interaction.channel_id)):
            return await interaction.response.send_message("Painel inativo ou desatualizado.", ephemeral=True)
        if panel.get("reversed"):
            return await interaction.response.send_message("Reversed não funciona com menus.", ephemeral=True)
        available = {role_id for _, role_id in selection_options(panel)}
        if not selected.issubset(available) or (panel.get("unique") and len(selected) > 1):
            return await interaction.response.send_message("Seleção inválida.", ephemeral=True)
        guild = interaction.guild
        me = guild.me
        if me is None or not me.guild_permissions.manage_roles:
            return await interaction.response.send_message("O bot precisa de Gerenciar Cargos.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with get_member_lock(guild.id, interaction.user.id):
            try:
                member = await guild.fetch_member(interaction.user.id)
                if member.bot:
                    return await interaction.followup.send("Bots não podem selecionar cargos.", ephemeral=True)
                current = {r.id for r in member.roles}
                add_ids = selected - current
                remove_ids = (current & available) - selected
                if panel.get("verify") or panel.get("binding"):
                    remove_ids.clear()
                if add_ids:
                    allowed, reason = can_change(panel, member, "grant")
                    if not allowed:
                        await record_audit(self.bot, self.store, guild.id, "denied", member_id=member.id, panel_id=self.panel_id, source="select", note=reason)
                        return await interaction.followup.send("❌ " + reason, ephemeral=True)
                if remove_ids:
                    allowed, reason = can_change(panel, member, "revoke")
                    if not allowed:
                        await record_audit(self.bot, self.store, guild.id, "denied", member_id=member.id, panel_id=self.panel_id, source="select", note=reason)
                        return await interaction.followup.send("❌ " + reason, ephemeral=True)
                changed = add_ids | remove_ids
                roles = {role_id: guild.get_role(role_id) for role_id in changed}
                if any(r is None or r.is_default() or r.managed or r >= me.top_role for r in roles.values()):
                    return await interaction.followup.send("Um dos cargos não pode ser gerenciado pelo bot.", ephemeral=True)
                # Process removals before grants to preserve Unique behavior.
                if remove_ids:
                    await member.remove_roles(*(roles[i] for i in remove_ids), reason="KING PLUS: menu de cargos")
                if add_ids:
                    await member.add_roles(*(roles[i] for i in add_ids), reason="KING PLUS: menu de cargos")
                for role_id in remove_ids:
                    await record_audit(self.bot, self.store, guild.id, "revoke", member_id=member.id, role_id=role_id, panel_id=self.panel_id, source="select")
                    await unregister_grant(self.store, guild.id, member.id, role_id)
                for role_id in add_ids:
                    await record_audit(self.bot, self.store, guild.id, "grant", member_id=member.id, role_id=role_id, panel_id=self.panel_id, source="select")
                if panel.get("temporary_seconds"):
                    for role_id in add_ids:
                        await register_grant(self.store, guild.id, member.id, role_id,
                                             panel["id"], panel["temporary_seconds"])
                await interaction.followup.send(
                    f"✅ Seleção atualizada: {len(add_ids)} adicionado(s), {len(remove_ids)} removido(s).",
                    ephemeral=True)
            except (discord.Forbidden, discord.HTTPException):
                await record_audit(self.bot, self.store, guild.id, "error", member_id=interaction.user.id, panel_id=self.panel_id, source="select", note="Falha na API do Discord")
                await interaction.followup.send("Não foi possível atualizar os cargos. Verifique permissões.", ephemeral=True)
