"""Comandos de logs e consulta ao histórico administrativo."""
import discord
from discord import app_commands
from discord.ext import commands
from modules.sugestoes.storage import read_data, mutate
from modules.sugestoes.permissions import can_review, is_manager
from modules.sugestoes.audit import record_event, send_audit_log

class HistoryView(discord.ui.View):
    def __init__(self, guild_id, owner_id, suggestion_id=None):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.suggestion_id = suggestion_id
        self.page = 0

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id or interaction.guild_id != self.guild_id:
            await interaction.response.send_message("Este painel pertence a outra pessoa.", ephemeral=True)
            return False
        return await can_review(interaction)

    async def render(self):
        data = await read_data(self.guild_id)
        events = data.get("audit_events", [])
        if self.suggestion_id is not None:
            events = [e for e in events if e.get("suggestion_id") == self.suggestion_id]
        events = list(reversed(events))
        total = max(1, (len(events) + 4) // 5)
        self.page = min(max(0, self.page), total - 1)
        selection = events[self.page * 5:self.page * 5 + 5]
        lines = []
        for e in selection:
            details = e.get("details", {})
            delta = ""
            if e.get("action") == "status_changed":
                delta = f" | {details.get('before', '?')} → {details.get('after', '?')}"
            # Autores de sugestões anônimas não são exibidos na auditoria visual.
            actor = "oculto" if e.get("action") == "suggestion_created" and details.get("anonymous") else str(e.get("actor_id", '?'))
            lines.append(f"**#{e['id']}** • `{e['action']}` • sugestão {e.get('suggestion_id') or '—'}\n"
                         f"{e.get('timestamp', '')[:19]} UTC • responsável: {actor}{delta}")
        embed = discord.Embed(title="📚 Histórico de sugestões",
            description="\n\n".join(lines) if lines else "Nenhum evento registrado ainda.",
            color=discord.Color.blurple())
        embed.set_footer(text=f"Página {self.page+1}/{total} • até 5000 eventos mantidos")
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= total - 1
        return embed

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        self.page -= 1
        await interaction.response.edit_message(embed=await self.render(), view=self)

    @discord.ui.button(label="Próxima", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        self.page += 1
        await interaction.response.edit_message(embed=await self.render(), view=self)

    @discord.ui.button(label="Atualizar", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction, button):
        await interaction.response.edit_message(embed=await self.render(), view=self)

class AuditPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="sugestao_logs_canal", description="Configura ou desativa o canal de logs")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs_canal(self, interaction: discord.Interaction, canal: discord.TextChannel | None = None):
        if not is_manager(interaction):
            return await interaction.response.send_message("Sem permissão.", ephemeral=True)
        def save(data):
            old = data.setdefault("settings", {}).get("audit_channel_id")
            data["settings"]["audit_channel_id"] = canal.id if canal else None
            record_event(data, "audit_channel_changed", interaction.user.id,
                         details={"before": old, "after": canal.id if canal else None})
        await mutate(interaction.guild_id, save)
        await interaction.response.send_message(
            f"Canal de logs: {canal.mention if canal else 'desativado'}.", ephemeral=True)
        if canal:
            await send_audit_log(self.bot, interaction.guild_id, "audit_channel_changed", interaction.user.id)

    @app_commands.command(name="sugestao_historico", description="Consulta a auditoria de sugestões")
    @app_commands.guild_only()
    @app_commands.describe(numero="ID da sugestão (opcional)")
    async def historico(self, interaction: discord.Interaction, numero: app_commands.Range[int, 1] | None = None):
        if not await can_review(interaction):
            return await interaction.response.send_message("Sem permissão para consultar o histórico.", ephemeral=True)
        view = HistoryView(interaction.guild_id, interaction.user.id, numero)
        await interaction.response.send_message(embed=await view.render(), view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AuditPanel(bot))
