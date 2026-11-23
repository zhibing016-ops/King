import discord
from discord import app_commands
from discord.ext import commands
from modules.sugestoes.storage import read_data, mutate
from modules.sugestoes.antispam import DEFAULTS


def authorized(interaction):
    return bool(interaction.guild and interaction.user.guild_permissions.manage_guild)


class ConfigModal(discord.ui.Modal, title="Configurar anti-spam"):
    cooldown = discord.ui.TextInput(label="Intervalo entre envios (segundos)", default="60", max_length=6)
    daily = discord.ui.TextInput(label="Máximo em 24 horas (0 = ilimitado)", default="5", max_length=5)
    duplicate = discord.ui.TextInput(label="Bloquear duplicadas por (segundos)", default="86400", max_length=7)

    async def on_submit(self, interaction):
        if not authorized(interaction):
            return await interaction.response.send_message("Sem permissão.", ephemeral=True)
        try:
            values = [int(self.cooldown.value), int(self.daily.value), int(self.duplicate.value)]
        except ValueError:
            return await interaction.response.send_message("Informe apenas números inteiros.", ephemeral=True)
        if not (0 <= values[0] <= 604800 and 0 <= values[1] <= 10000 and 0 <= values[2] <= 2592000):
            return await interaction.response.send_message("Valores fora dos limites permitidos.", ephemeral=True)
        def update(data):
            cfg = data.setdefault("settings", {}).setdefault("antispam", {})
            cfg.update(zip(("cooldown_seconds", "daily_limit", "duplicate_window_seconds"), values))
        await mutate(interaction.guild_id, update)
        await interaction.response.send_message("Configurações anti-spam atualizadas.", ephemeral=True)


class ConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Configurar limites", emoji="⚙️", style=discord.ButtonStyle.primary)
    async def limits(self, interaction, button):
        if not authorized(interaction):
            return await interaction.response.send_message("Sem permissão.", ephemeral=True)
        data = await read_data(interaction.guild_id)
        cfg = {**DEFAULTS, **data.get("settings", {}).get("antispam", {})}
        modal = ConfigModal()
        modal.cooldown.default = str(cfg["cooldown_seconds"])
        modal.daily.default = str(cfg["daily_limit"])
        modal.duplicate.default = str(cfg["duplicate_window_seconds"])
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Ativar / Desativar", emoji="🛡️", style=discord.ButtonStyle.secondary)
    async def toggle(self, interaction, button):
        if not authorized(interaction):
            return await interaction.response.send_message("Sem permissão.", ephemeral=True)
        def update(data):
            cfg = data.setdefault("settings", {}).setdefault("antispam", {})
            cfg["enabled"] = not cfg.get("enabled", True)
            return cfg["enabled"]
        active = await mutate(interaction.guild_id, update)
        await interaction.response.send_message(f"Anti-spam {'ativado' if active else 'desativado'}.", ephemeral=True)


class AntispamSettings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="sugestao_antispam", description="Painel de limites e proteção contra spam")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def antispam(self, interaction: discord.Interaction):
        data = await read_data(interaction.guild_id)
        cfg = {**DEFAULTS, **data.get("settings", {}).get("antispam", {})}
        embed = discord.Embed(title="🛡️ KING PLUS • Anti-spam", description=(
            f"Ativo: **{'Sim' if cfg['enabled'] else 'Não'}**\n"
            f"Cooldown: **{cfg['cooldown_seconds']} s**\n"
            f"Limite em 24h: **{cfg['daily_limit']}** (0 = ilimitado)\n"
            f"Duplicadas: **{cfg['duplicate_window_seconds']} s** (0 = desativado)"))
        await interaction.response.send_message(embed=embed, view=ConfigView(), ephemeral=True)

    @app_commands.command(name="sugestao_bloquear", description="Bloqueia ou desbloqueia um membro de enviar sugestões")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bloquear(self, interaction: discord.Interaction, membro: discord.Member, bloquear: bool):
        def update(data):
            settings = data.setdefault("settings", {})
            blocked = set(settings.get("suggestion_blocked_ids", []))
            if bloquear:
                blocked.add(membro.id)
            else:
                blocked.discard(membro.id)
            settings["suggestion_blocked_ids"] = sorted(blocked)
        await mutate(interaction.guild_id, update)
        await interaction.response.send_message(f"{membro.mention}: {'bloqueado' if bloquear else 'desbloqueado'} para sugestões.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AntispamSettings(bot))
