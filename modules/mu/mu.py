"""Painel MU: único comando /mu. Requer cogs.listas e cogs.alarmes."""
import discord
from discord import app_commands
from discord.ext import commands
from .config import load_config, save_config
from . import listas, alarmes


def admin(interaction):
    return bool(interaction.guild and interaction.user.guild_permissions.administrator)

class ConfigCanal(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="Canal para avisos", channel_types=[discord.ChannelType.text], custom_id="mu:canal_alertas")

    async def callback(self, interaction):
        if not admin(interaction):
            return await interaction.response.send_message("Apenas administradores.", ephemeral=True)
        canal = self.values[0]
        cfg = load_config()
        cfg['canal_alertas'] = canal.id
        save_config(cfg)
        await interaction.response.send_message(f"Notificações serão enviadas em {canal.mention}.", ephemeral=True)

class ConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(ConfigCanal())

class MUView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Leilão Guild", emoji="📋", style=discord.ButtonStyle.primary, custom_id="mu:leilao")
    async def leilao(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=discord.Embed(title="📋 Leilão Guild", description="Gerencie as listas usando os botões abaixo.", color=discord.Color.blurple()), view=listas.ListaPainel(), ephemeral=True)

    @discord.ui.button(label="Notificações", emoji="🔔", style=discord.ButtonStyle.secondary, custom_id="mu:notificacoes")
    async def notificacoes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=alarmes.build_alarmes_embed(), view=alarmes.AlarmesView(), ephemeral=True)

    @discord.ui.button(label="Canal de avisos", emoji="⚙️", style=discord.ButtonStyle.secondary, custom_id="mu:config")
    async def config(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not admin(interaction):
            return await interaction.response.send_message("Apenas administradores.", ephemeral=True)
        await interaction.response.send_message("Selecione o canal para as notificações:", view=ConfigView(), ephemeral=True)

class MU(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mu", description="Publicar o painel principal MU")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.check(admin)
    async def mu(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🎮 Painel MU", description="Selecione **Leilão Guild** ou **Notificações**.", color=discord.Color.blurple())
        await interaction.response.send_message("Publicando o painel…", ephemeral=True)
        try:
            cfg = load_config()
            old = cfg.get('painel_mu', {})
            channel = self.bot.get_channel(old.get('canal_id')) if old.get('canal_id') else None
            if channel and old.get('mensagem_id'):
                try:
                    msg = await channel.fetch_message(old['mensagem_id'])
                    await msg.edit(embed=embed, view=MUView())
                    await interaction.followup.send(f"Painel atualizado: {msg.jump_url}", ephemeral=True)
                    return
                except (discord.NotFound, discord.Forbidden):
                    pass
            msg = await interaction.channel.send(embed=embed, view=MUView())
            try:
                await msg.pin()
            except discord.Forbidden:
                pass
            cfg['painel_mu'] = {'canal_id': interaction.channel_id, 'mensagem_id': msg.id}
            save_config(cfg)
            await interaction.followup.send(f"Painel publicado: {msg.jump_url}", ephemeral=True)
        except discord.HTTPException:
            await interaction.followup.send("Não consegui publicar. Confira minhas permissões de enviar mensagens e embeds.", ephemeral=True)

async def setup(bot):
    bot.add_view(MUView())
    await bot.add_cog(MU(bot))
