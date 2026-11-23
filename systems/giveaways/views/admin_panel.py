import discord


def is_admin(interaction: discord.Interaction) -> bool:
    return bool(interaction.guild and interaction.user.guild_permissions.manage_guild)


class AdminPanel(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=600)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction):
            await interaction.response.send_message("⛔ Você precisa de Gerenciar Servidor para usar este painel.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Criar sorteio", emoji="🎁", style=discord.ButtonStyle.success, row=0)
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = await self.cog.store.get_guild(interaction.guild_id)
        if not guild.get("enabled", True):
            return await interaction.response.send_message("🛠️ Sistema desativado para manutenção.", ephemeral=True)
        from .create_panel import ChannelPicker
        await interaction.response.send_message("🎁 Selecione o canal para publicar o sorteio:", view=ChannelPicker(self.cog), ephemeral=True)

    @discord.ui.button(label="Sorteios ativos", emoji="📋", style=discord.ButtonStyle.primary, row=0)
    async def active(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .manage_panel import show_manage
        await show_manage(interaction, self.cog)

    @discord.ui.button(label="Configurações", emoji="⚙️", style=discord.ButtonStyle.secondary, row=0)
    async def config(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = await self.cog.store.get_guild(interaction.guild_id)
        await interaction.response.send_message(
            "⚙️ **Configurações**\nEstado: **{}**\nArmazenamento: **JSON**".format("Ativado" if guild.get("enabled", True) else "Desativado"),
            view=SettingsPanel(self.cog), ephemeral=True)

    @discord.ui.button(label="Aparência", emoji="🎨", style=discord.ButtonStyle.secondary, row=1)
    async def appearance(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .appearance_panel import AppearancePanel
        await interaction.response.send_message('🎨 Personalize os próximos sorteios, visualize ou restaure o padrão.', view=AppearancePanel(self.cog), ephemeral=True)

    @discord.ui.button(label="Vencedores", emoji="🏆", style=discord.ButtonStyle.secondary, row=1)
    async def winners(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .reroll_panel import show_reroll
        await show_reroll(interaction, self.cog)

    @discord.ui.button(label="Agendamentos", emoji="📅", style=discord.ButtonStyle.primary, row=2)
    async def schedules(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .schedule_panel import show_schedule
        await show_schedule(interaction, self.cog)

    @discord.ui.button(label="Estatísticas", emoji="📊", style=discord.ButtonStyle.secondary, row=3)
    async def statistics(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .stats_panel import show_statistics
        await show_statistics(interaction, self.cog)

    @discord.ui.button(label="Manutenção", emoji="🛠️", style=discord.ButtonStyle.secondary, row=3)
    async def maintenance(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🛠️ **Manutenção e auditoria**", view=MaintenancePanel(self.cog), ephemeral=True)

    @discord.ui.button(label="Requisitos", emoji="🛡️", style=discord.ButtonStyle.secondary, row=2)
    async def requirements(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🛡️ **Requisitos de participação**", view=RequirementsPanel(self.cog), ephemeral=True)


class SettingsPanel(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=600)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction):
            await interaction.response.send_message("⛔ Você precisa de Gerenciar Servidor.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Ativar", emoji="✅", style=discord.ButtonStyle.success)
    async def enable(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.store.set_enabled(interaction.guild_id, True)
        await interaction.response.edit_message(content="✅ Sistema de sorteios ativado.", view=SettingsPanel(self.cog))

    @discord.ui.button(label="Desativar", emoji="🛠️", style=discord.ButtonStyle.danger)
    async def disable(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.store.set_enabled(interaction.guild_id, False)
        await interaction.response.edit_message(content="🛠️ Sistema desativado para manutenção.", view=SettingsPanel(self.cog))

    @discord.ui.button(label="Voltar ao painel", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = await self.cog.store.get_guild(interaction.guild_id)
        await interaction.response.edit_message(content=None, embed=self.cog.make_panel_embed(guild), view=AdminPanel(self.cog))


class RequirementsModal(discord.ui.Modal, title="Requisitos de sorteios"):
    dias = discord.ui.TextInput(label="Dias mínimos no servidor", default="0", max_length=3)
    cargo = discord.ui.TextInput(label="ID do cargo (vazio = nenhum)", required=False, max_length=22)
    dias_conta = discord.ui.TextInput(label="Dias mínimos da conta", default="0", max_length=4)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction):
        try:
            dias, idade = int(self.dias.value), int(self.dias_conta.value)
            if not (0 <= dias <= 365 and 0 <= idade <= 3650): raise ValueError()
            role = None
            if self.cargo.value.strip():
                role = interaction.guild.get_role(int(self.cargo.value.strip()))
                if role is None: return await interaction.response.send_message("Cargo não encontrado.", ephemeral=True)
        except ValueError:
            return await interaction.response.send_message("Informe números válidos.", ephemeral=True)
        await self.cog.store.set_requirements(interaction.guild_id, role.id if role else None, dias)
        await self.cog.store.set_account_age_requirement(interaction.guild_id, idade)
        await interaction.response.send_message("✅ Requisitos atualizados para os próximos sorteios.", ephemeral=True)


class RequirementsPanel(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=600)
        self.cog = cog

    async def interaction_check(self, interaction):
        if not is_admin(interaction):
            await interaction.response.send_message("Requer Gerenciar Servidor.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Editar requisitos", emoji="🛡️")
    async def edit(self, interaction, button):
        await interaction.response.send_modal(RequirementsModal(self.cog))


class MaintenancePanel(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=600)
        self.cog = cog

    async def interaction_check(self, interaction):
        if not is_admin(interaction):
            await interaction.response.send_message("Requer Gerenciar Servidor.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Diagnóstico", emoji="🔍", row=0)
    async def diagnosis(self, interaction, button):
        await self.cog.sorteio_diagnostico(interaction)

    @discord.ui.button(label="Histórico", emoji="📜", row=0)
    async def history(self, interaction, button):
        await self.cog.sorteio_historico(interaction)

    @discord.ui.button(label="Canal de logs", emoji="📝", row=0)
    async def logs(self, interaction, button):
        await interaction.response.send_message("Escolha o canal de auditoria:", view=LogChannelPanel(self.cog), ephemeral=True)

    @discord.ui.button(label="Exportar backup", emoji="📦", row=1)
    async def backup(self, interaction, button):
        await self.cog.sorteio_backup(interaction)

    @discord.ui.button(label="Restaurar backup", emoji="♻️", row=1)
    async def restore(self, interaction, button):
        await interaction.response.send_message("Para restaurar, envie um arquivo JSON ao administrador responsável. A restauração por anexo exige um fluxo de upload separado; nenhum dado foi alterado.", ephemeral=True)


class LogChannelPanel(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=600)
        self.cog=cog

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Selecionar canal de logs")
    async def select(self, interaction, select):
        if not is_admin(interaction):
            return await interaction.response.send_message("Requer Gerenciar Servidor.", ephemeral=True)
        await self.cog.sorteio_logs_canal(interaction, select.values[0])
