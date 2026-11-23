"""Fase 07: configuração de cargos da equipe dentro do Discord."""
import discord
from discord import app_commands
from discord.ext import commands
from modules.sugestoes.storage import read_data, mutate
from modules.sugestoes.permissions import is_manager


class RolePicker(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Selecionar cargos da equipe", min_values=1, max_values=10)

    async def callback(self, interaction: discord.Interaction):
        if not is_manager(interaction):
            return await interaction.response.send_message("Somente Gerenciar Servidor pode configurar cargos.", ephemeral=True)
        ids = [role.id for role in self.values if not role.is_default() and not role.managed]
        if not ids:
            return await interaction.response.send_message("Escolha cargos comuns do servidor.", ephemeral=True)
        def save(data):
            data.setdefault("settings", {})["review_role_ids"] = ids
        await mutate(interaction.guild_id, save)
        await interaction.response.send_message("Equipe atualizada: " + ", ".join(f"<@&{x}>" for x in ids), ephemeral=True)


class TeamView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)
        self.add_item(RolePicker())

    @discord.ui.button(label="Remover todos os cargos", style=discord.ButtonStyle.danger)
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_manager(interaction):
            return await interaction.response.send_message("Sem permissão.", ephemeral=True)
        def save(data):
            data.setdefault("settings", {})["review_role_ids"] = []
        await mutate(interaction.guild_id, save)
        await interaction.response.send_message("Cargos da equipe removidos.", ephemeral=True)


class SuggestionTeam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="sugestao_equipe", description="Configura os cargos da equipe de sugestões")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sugestao_equipe(self, interaction: discord.Interaction):
        data = await read_data(interaction.guild_id)
        ids = data.get("settings", {}).get("review_role_ids", [])
        embed = discord.Embed(title="🛡️ KING PLUS • Equipe de Sugestões",
            description="**Cargos autorizados:** " + (", ".join(f"<@&{i}>" for i in ids) if ids else "Nenhum") +
            "\n\nSelecione até 10 cargos para analisar, aprovar e rejeitar sugestões. "
            "Membros com Gerenciar Servidor mantêm acesso administrativo.",
            color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=TeamView(), ephemeral=True)


async def setup(bot):
    await bot.add_cog(SuggestionTeam(bot))
