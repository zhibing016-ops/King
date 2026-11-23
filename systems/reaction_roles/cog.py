"""Comandos administrativos iniciais do Reaction Roles."""
import discord
from discord import app_commands
from discord.ext import commands, tasks

from .storage.json_store import GuildJsonStore
from .views.admin_panel import AdminPanel
from .services.reactions import handle_raw_reaction
from .services.expiry import process_expirations
from .views.interface_mode import panel_view

class ReactionRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = GuildJsonStore()
        self.expiration_worker.start()
        self._views_registered = False

    def cog_unload(self):
        self.expiration_worker.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if self._views_registered:
            return
        for guild in self.bot.guilds:
            data = await self.store.get(guild.id)
            for panel in data.get("panels", {}).values():
                if (panel.get("interface") in ("buttons", "select") and panel.get("message_id")
                        and panel.get("roles")):
                    self.bot.add_view(panel_view(self.bot, self.store, guild.id, panel),
                                      message_id=int(panel["message_id"]))
        self._views_registered = True

    @tasks.loop(seconds=60)
    async def expiration_worker(self):
        await process_expirations(self.bot, self.store)

    @expiration_worker.before_loop
    async def before_expiration_worker(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name='reactionroles', description='Abrir o painel principal do Reaction Roles KING PLUS')
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reactionroles(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            return await interaction.response.send_message('Use este comando em um servidor.', ephemeral=True)
        await self.store.initialize(interaction.guild_id)
        from .views.dashboard import ReactionRolesDashboard
        view = ReactionRolesDashboard(self.store, interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=await view.make_embed(), view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await handle_raw_reaction(self.bot, self.store, payload, True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await handle_raw_reaction(self.bot, self.store, payload, False)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            message = '❌ Você precisa da permissão Gerenciar Servidor.'
        else:
            message = '❌ Não foi possível executar o comando. Consulte os logs do bot.'
            import logging
            logging.getLogger(__name__).error('Erro no Reaction Roles: %r', error)
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))
