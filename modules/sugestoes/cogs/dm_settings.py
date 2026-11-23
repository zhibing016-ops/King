"""Fase 08: preferências de notificação."""
import discord
from discord import app_commands
from discord.ext import commands
from modules.sugestoes.storage import read_data, mutate

class DmSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="sugestao_notificacoes", description="Configura notificações por DM das sugestões")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def notificacoes(self, interaction: discord.Interaction, ativar: bool):
        def salvar(data):
            data.setdefault("settings", {})["dm_enabled"] = ativar
        await mutate(interaction.guild_id, salvar)
        await interaction.response.send_message("Notificações por DM " + ("ativadas." if ativar else "desativadas."), ephemeral=True)

    @app_commands.command(name="sugestao_notificar_status", description="Escolhe quais mudanças de status enviam DM")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.choices(status=[app_commands.Choice(name=s, value=s) for s in ("Aprovada", "Rejeitada", "Em análise")])
    async def notificar_status(self, interaction: discord.Interaction, status: app_commands.Choice[str], ativar: bool):
        def salvar(data):
            data.setdefault("settings", {}).setdefault("dm_statuses", {})[status.value] = ativar
        await mutate(interaction.guild_id, salvar)
        await interaction.response.send_message(f"DM para **{status.value}**: {'ativada' if ativar else 'desativada'}.", ephemeral=True)

    @app_commands.command(name="sugestao_minhas_dms", description="Ativa ou desativa DMs sobre suas próprias sugestões")
    @app_commands.guild_only()
    async def minhas_dms(self, interaction: discord.Interaction, receber: bool):
        def salvar(data):
            settings = data.setdefault("settings", {})
            optout = set(map(str, settings.get("dm_opt_out", [])))
            if receber:
                optout.discard(str(interaction.user.id))
            else:
                optout.add(str(interaction.user.id))
            settings["dm_opt_out"] = sorted(optout)
        await mutate(interaction.guild_id, salvar)
        await interaction.response.send_message("Sua preferência de DM foi atualizada.", ephemeral=True)

    @app_commands.command(name="sugestao_config_dms", description="Mostra a configuração atual de notificações")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_dms(self, interaction: discord.Interaction):
        data = await read_data(interaction.guild_id)
        settings = data.get("settings", {})
        lines = [f"Notificações gerais: {'Ativas' if settings.get('dm_enabled', True) else 'Desativadas'}"]
        for status in ("Em análise", "Aprovada", "Rejeitada"):
            lines.append(f"{status}: {'Ativas' if settings.get('dm_statuses', {}).get(status, True) else 'Desativadas'}")
        embed = discord.Embed(title="🔔 KING PLUS • Configuração de DMs", description="\n".join(lines), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(DmSettings(bot))
