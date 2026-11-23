import discord
from discord import app_commands
from discord.ext import commands
from modules.sugestoes.storage import mutate
from modules.sugestoes.maintenance import diagnostic, make_backup, parse_backup, restore


def manager(interaction):
    return bool(interaction.guild and interaction.user.guild_permissions.manage_guild)


class ConfirmRestore(discord.ui.View):
    def __init__(self, user_id, guild_id, data):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id
        self.data = data

    async def interaction_check(self, interaction):
        if interaction.guild_id != self.guild_id or interaction.user.id != self.user_id or not manager(interaction):
            await interaction.response.send_message("Acesso negado.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirmar restauração", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        # Segurança: mantém manutenção ativada após restaurar.
        self.data.setdefault("settings", {})["maintenance_enabled"] = True
        await restore(self.guild_id, self.data)
        from modules.sugestoes.recovery import register_vote_views
        recovered = await register_vote_views(interaction.client, self.guild_id)
        self.stop()
        await interaction.followup.send(f"Backup restaurado. Manutenção permanece ativada; confira os dados antes de reativar. Botões recuperados nesta sessão: {recovered}. Reinicie o bot se mensagens antigas tiverem sido removidas ou alteradas.", ephemeral=True)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self.stop()
        await interaction.response.edit_message(content="Restauração cancelada.", view=None)


class MaintenancePanel(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id or not manager(interaction):
            await interaction.response.send_message("Acesso negado.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Diagnóstico", emoji="🔎", style=discord.ButtonStyle.secondary)
    async def diagnose(self, interaction, button):
        result = await diagnostic(interaction.guild_id)
        lines = "\n".join(result["issues"]) if result["issues"] else "Nenhum problema estrutural detectado."
        await interaction.response.send_message(f"Sugestões: {result['suggestions']} | Manutenção: {result['maintenance']}\n{lines[:1500]}", ephemeral=True)

    @discord.ui.button(label="Ativar manutenção", style=discord.ButtonStyle.danger)
    async def enable(self, interaction, button):
        await mutate(interaction.guild_id, lambda d: d.setdefault("settings", {}).__setitem__("maintenance_enabled", True))
        await interaction.response.send_message("Manutenção ativada. Novas sugestões estão bloqueadas.", ephemeral=True)

    @discord.ui.button(label="Desativar manutenção", style=discord.ButtonStyle.success)
    async def disable(self, interaction, button):
        await mutate(interaction.guild_id, lambda d: d.setdefault("settings", {}).__setitem__("maintenance_enabled", False))
        await interaction.response.send_message("Manutenção desativada.", ephemeral=True)

    @discord.ui.button(label="Criar backup", emoji="💾", style=discord.ButtonStyle.primary, row=1)
    async def backup(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        try:
            content = await make_backup(interaction.guild_id)
            await interaction.followup.send("Backup JSON do servidor:", file=discord.File(content, filename=f"kingplus_backup_{interaction.guild_id}.json"), ephemeral=True)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)


class Maintenance(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="sugestao_manutencao", description="Painel de manutenção e diagnóstico")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def painel(self, interaction: discord.Interaction):
        await interaction.response.send_message("**KING PLUS • Manutenção**\nGerencie o estado do sistema, faça backup e execute diagnóstico.", view=MaintenancePanel(interaction.user.id), ephemeral=True)

    @app_commands.command(name="sugestao_restaurar", description="Restaura backup JSON do mesmo servidor (substitui dados atuais)")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def restaurar(self, interaction: discord.Interaction, arquivo: discord.Attachment):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            if arquivo.size > 8 * 1024 * 1024: raise ValueError("Arquivo maior que 8 MiB.")
            data = parse_backup(await arquivo.read(), interaction.guild_id)
        except (ValueError, discord.HTTPException) as exc:
            return await interaction.followup.send(f"Backup recusado: {exc}", ephemeral=True)
        await interaction.followup.send("**Atenção:** a restauração substituirá sugestões, votos, configurações e histórico atuais. Crie um backup antes. Confirme em até 2 minutos.", view=ConfirmRestore(interaction.user.id, interaction.guild_id, data), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Maintenance(bot))
