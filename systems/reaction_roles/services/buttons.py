"""Persisted button-role panels and safe role toggles."""
import discord
from .reactions import get_member_lock
from .unique import conflicting_role_ids
from .temporary import register_grant, unregister_grant
from .access import can_change
from .audit import record_audit

def button_entries(panel):
    return list(panel.get("roles", {}).items())[:20]

def make_button_view(bot, store, guild_id, panel):
    return RoleButtonView(bot, store, guild_id, panel["id"], panel)

class RoleButton(discord.ui.Button):
    def __init__(self, emoji, role_id, panel_id, index):
        # Labels do not require access to the guild cache.
        super().__init__(label=f"Cargo {index + 1}", style=discord.ButtonStyle.secondary,
                         custom_id=f"kingplus:rr:button:{panel_id}:{int(role_id)}")
        try:
            self.emoji = discord.PartialEmoji.from_str(emoji)
        except (TypeError, ValueError):
            pass

    async def callback(self, interaction):
        await self.view.toggle(interaction, int(self.custom_id.rsplit(":", 1)[1]))

class RoleButtonView(discord.ui.View):
    def __init__(self, bot, store, guild_id, panel_id, panel):
        super().__init__(timeout=None)
        self.bot, self.store, self.guild_id, self.panel_id = bot, store, guild_id, panel_id
        for index, (emoji, role_id) in enumerate(button_entries(panel)):
            self.add_item(RoleButton(emoji, role_id, panel_id, index))

    async def toggle(self, interaction, role_id):
        if not interaction.guild or interaction.guild.id != self.guild_id:
            return await interaction.response.send_message("Servidor inválido.", ephemeral=True)
        guild = interaction.guild
        data = await self.store.get(guild.id)
        panel = data.get("panels", {}).get(self.panel_id)
        if (not data.get("enabled") or not panel or panel.get("interface", "reactions") != "buttons"
                or str(role_id) not in [str(v) for v in panel.get("roles", {}).values()]
                or str(interaction.message.id) != str(panel.get("message_id"))):
            return await interaction.response.send_message("Este painel não está mais ativo.", ephemeral=True)
        if panel.get("reversed"):
            return await interaction.response.send_message("O modo Reversed usa reações. Altere o modo do painel.", ephemeral=True)
        role = guild.get_role(role_id)
        me = guild.me
        if (role is None or role.is_default() or role.managed or me is None
                or not me.guild_permissions.manage_roles or role >= me.top_role):
            return await interaction.response.send_message("Não tenho permissão para gerenciar este cargo.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        lock = get_member_lock(guild.id, interaction.user.id)
        async with lock:
            try:
                member = await guild.fetch_member(interaction.user.id)
                if member.bot:
                    return await interaction.followup.send("Bots não podem usar este painel.", ephemeral=True)
                allowed, reason = can_change(panel, member, "revoke" if role in member.roles else "grant")
                if not allowed:
                    await record_audit(self.bot, self.store, guild.id, 'denied', member_id=member.id, role_id=role.id, panel_id=self.panel_id, source='button', note=reason)
                    return await interaction.followup.send("❌ " + reason, ephemeral=True)
                if role in member.roles:
                    if panel.get("verify") or panel.get("binding"):
                        return await interaction.followup.send("Este cargo é permanente neste painel.", ephemeral=True)
                    await member.remove_roles(role, reason="KING PLUS: botão de cargo")
                    await unregister_grant(self.store, guild.id, member.id, role.id)
                    await record_audit(self.bot, self.store, guild.id, "revoke", member_id=member.id, role_id=role.id, panel_id=self.panel_id, source="button")
                    return await interaction.followup.send(f"➖ Cargo {role.mention} removido.", ephemeral=True)
                if panel.get("unique"):
                    conflicts = conflicting_role_ids(panel, role_id)
                    removable = [r for r in member.roles if r.id in conflicts]
                    if any(r.managed or r >= me.top_role for r in removable):
                        return await interaction.followup.send("Não posso remover um cargo exclusivo conflitante.", ephemeral=True)
                    if removable:
                        await member.remove_roles(*removable, reason="KING PLUS: modo Unique")
                await member.add_roles(role, reason="KING PLUS: botão de cargo")
                await record_audit(self.bot, self.store, guild.id, "grant", member_id=member.id, role_id=role.id, panel_id=self.panel_id, source="button")
                if panel.get("temporary_seconds"):
                    await register_grant(self.store, guild.id, member.id, role.id, panel["id"], panel["temporary_seconds"])
                await interaction.followup.send(f"✅ Cargo {role.mention} adicionado.", ephemeral=True)
            except (discord.Forbidden, discord.HTTPException):
                await record_audit(self.bot, self.store, guild.id, "error", member_id=interaction.user.id, role_id=role.id, panel_id=self.panel_id, source="button", note="Falha na API do Discord")
                await interaction.followup.send("Falha ao atualizar o cargo. Confira as permissões.", ephemeral=True)
