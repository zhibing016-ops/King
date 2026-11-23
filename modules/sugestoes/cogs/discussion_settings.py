import discord
from discord import app_commands
from discord.ext import commands
from modules.sugestoes.storage import read_data, mutate

class DiscussionSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="sugestao_discussao", description="Configura tópicos e comentários das novas sugestões")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def discussao(self, interaction: discord.Interaction, topicos: bool, comentarios: bool):
        def save(data):
            data.setdefault("settings", {}).update(threads_enabled=topicos, comments_enabled=comentarios)
        await mutate(interaction.guild_id, save)
        await interaction.response.send_message(f"Tópicos: {'ativados' if topicos else 'desativados'}; comentários: {'ativados' if comentarios else 'desativados'}.", ephemeral=True)

    @app_commands.command(name="sugestao_imagens", description="Permite ou bloqueia imagens nas novas sugestões")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def imagens(self, interaction: discord.Interaction, permitir: bool):
        def save(data):
            data.setdefault("settings", {})["images_enabled"] = permitir
        await mutate(interaction.guild_id, save)
        await interaction.response.send_message("Imagens " + ("ativadas." if permitir else "desativadas."), ephemeral=True)

    @app_commands.command(name="sugestao_discussao_config", description="Mostra as configurações de discussão")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def config(self, interaction: discord.Interaction):
        s = (await read_data(interaction.guild_id)).get("settings", {})
        await interaction.response.send_message(
            f"Tópicos: **{s.get('threads_enabled', True)}**\nComentários: **{s.get('comments_enabled', True)}**\nImagens: **{s.get('images_enabled', True)}**", ephemeral=True)

async def setup(bot):
    await bot.add_cog(DiscussionSettings(bot))
