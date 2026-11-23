"""Painel administrativo temporário (ephemeral) da Fase 2."""
import logging
import discord

logger = logging.getLogger(__name__)

class AdminPanel(discord.ui.View):
    def __init__(self, store, guild_id: int, owner_id: int):
        super().__init__(timeout=300)
        self.store = store
        self.guild_id = guild_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        member = interaction.user
        if (interaction.guild_id != self.guild_id or member.id != self.owner_id
                or not isinstance(member, discord.Member)
                or not member.guild_permissions.manage_guild):
            await interaction.response.send_message('❌ Apenas o administrador que abriu este painel pode utilizá-lo.', ephemeral=True)
            return False
        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        logger.exception('Falha no painel de Reaction Roles', exc_info=error)
        msg = '❌ Ocorreu um erro. Consulte os logs do bot.'
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    async def make_embed(self):
        data = await self.store.get(self.guild_id)
        enabled = data.get('enabled', False)
        embed = discord.Embed(title='👑 KING PLUS • Reaction Roles',
                              description='Gerencie as configurações do sistema neste servidor.',
                              color=discord.Color.green() if enabled else discord.Color.red())
        embed.add_field(name='Sistema', value='🟢 Ativado' if enabled else '🔴 Desativado', inline=True)
        embed.add_field(name='Painéis cadastrados', value=str(len(data.get('panels', {}))), inline=True)
        embed.add_field(name='Armazenamento', value='JSON • por servidor', inline=False)
        embed.add_field(name='Gerenciamento', value='Criar, publicar e configurar emojis/cargos', inline=False)
        embed.set_footer(text='Fase 16/16 • Final • Diagnóstico e backup')
        return embed

    @discord.ui.button(label='Ativar / Desativar', emoji='⚙️', style=discord.ButtonStyle.primary, row=0)
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = await self.store.toggle_enabled(self.guild_id)
        await interaction.response.edit_message(embed=await self.make_embed(), view=self)

    @discord.ui.button(label='Atualizar', emoji='🔄', style=discord.ButtonStyle.secondary, row=0)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=await self.make_embed(), view=self)

    @discord.ui.button(label='Configurar painéis', emoji='🧩', style=discord.ButtonStyle.secondary, row=1)
    async def panels(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .panels import PanelManager
        view = PanelManager(self.store, self.guild_id, self.owner_id)
        await interaction.response.send_message(embed=await view.make_embed(), view=view, ephemeral=True)

    @discord.ui.button(label='Emojis e cargos', emoji='🎭', style=discord.ButtonStyle.secondary, row=2)
    async def mappings(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .role_mappings import MappingManager
        await interaction.response.send_message('**Gerenciar associações de emojis e cargos**', view=MappingManager(self.store, self.guild_id, self.owner_id), ephemeral=True)

    @discord.ui.button(label='Modo Unique', emoji='🔐', style=discord.ButtonStyle.secondary, row=2)
    async def unique(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .unique_mode import UniqueModeView
        panels = (await self.store.get(self.guild_id)).get('panels', {})
        if not panels:
            await interaction.response.send_message('Crie um painel primeiro.', ephemeral=True)
            return
        await interaction.response.send_message('**Modo Unique:** apenas um cargo por painel. Selecione para ativar ou desativar:', view=UniqueModeView(self.store, self.guild_id, self.owner_id, panels), ephemeral=True)

    @discord.ui.button(label='Modo Verify', emoji='✅', style=discord.ButtonStyle.secondary, row=3)
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .verify_mode import VerifyModeView
        panels = (await self.store.get(self.guild_id)).get('panels', {})
        if not panels:
            await interaction.response.send_message('Crie um painel primeiro.', ephemeral=True)
            return
        await interaction.response.send_message(
            '**Modo Verify:** uma reação concede o cargo de verificado; remover a reação não remove o cargo. Selecione o painel:',
            view=VerifyModeView(self.store, self.guild_id, self.owner_id, panels), ephemeral=True)

    async def open_advanced_mode(self, interaction, mode):
        from .advanced_modes import AdvancedModeView
        panels = (await self.store.get(self.guild_id)).get('panels', {})
        if not panels:
            await interaction.response.send_message('Crie um painel primeiro.', ephemeral=True)
            return
        await interaction.response.send_message(
            f'**Modo {mode.title()}**: selecione um painel para ativar/desativar.',
            view=AdvancedModeView(self.store, self.guild_id, self.owner_id, panels, mode), ephemeral=True)

    @discord.ui.button(label='Reversed', emoji='🔁', style=discord.ButtonStyle.secondary, row=3)
    async def reversed_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.open_advanced_mode(interaction, 'reversed')

    @discord.ui.button(label='Binding', emoji='🔗', style=discord.ButtonStyle.secondary, row=4)
    async def binding_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.open_advanced_mode(interaction, 'binding')

    @discord.ui.button(label='Temporários', emoji='⏱️', style=discord.ButtonStyle.secondary, row=4)
    async def temporary(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .temporary_mode import TemporaryModeView
        panels = (await self.store.get(self.guild_id)).get('panels', {})
        if not panels:
            await interaction.response.send_message('Crie um painel primeiro.', ephemeral=True)
            return
        await interaction.response.send_message('**Cargos temporários:** selecione um painel e configure a duração.',
            view=TemporaryModeView(self.store, self.guild_id, self.owner_id, panels), ephemeral=True)

    @discord.ui.button(label='Interfaces de cargos', emoji='🔘', style=discord.ButtonStyle.secondary, row=4)
    async def interfaces(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .interface_mode import InterfaceModeView
        panels = (await self.store.get(self.guild_id)).get("panels", {})
        if not panels:
            return await interaction.response.send_message("Crie um painel primeiro.", ephemeral=True)
        await interaction.response.send_message(
            "Escolha entre reações, botões ou menus de seleção:",
            view=InterfaceModeView(self.store, self.guild_id, self.owner_id, panels),
            ephemeral=True)

    @discord.ui.button(label='Personalizar embeds', emoji='🎨', style=discord.ButtonStyle.secondary, row=2)
    async def customize(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .customization import CustomizeManager
        panels = (await self.store.get(self.guild_id)).get('panels', {})
        if not panels:
            return await interaction.response.send_message('Crie um painel primeiro.', ephemeral=True)
        await interaction.response.send_message('Escolha um painel:', view=CustomizeManager(self.store, self.guild_id, self.owner_id, panels), ephemeral=True)

    @discord.ui.button(label='Restrições de acesso', emoji='🛡️', style=discord.ButtonStyle.secondary, row=3)
    async def access_control(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .access_control import AccessManager
        panels = (await self.store.get(self.guild_id)).get("panels", {})
        if not panels:
            return await interaction.response.send_message("Crie um painel primeiro.", ephemeral=True)
        await interaction.response.send_message("Escolha o painel para configurar permissões:",
            view=AccessManager(self.store, self.guild_id, self.owner_id, panels), ephemeral=True)

    @discord.ui.button(label='Logs e auditoria', emoji='📋', style=discord.ButtonStyle.secondary, row=0)
    async def audit(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .audit_panel import AuditView
        await interaction.response.send_message('Configure o canal e consulte o histórico de atividades:',
            view=AuditView(self.store, self.guild_id, self.owner_id), ephemeral=True)

    @discord.ui.button(label='Estatísticas', emoji='📊', style=discord.ButtonStyle.secondary, row=0)
    async def statistics(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .statistics_panel import StatisticsView
        await interaction.response.send_message(
            '**Estatísticas de Reaction Roles** • Selecione o período para consultar o relatório:',
            view=StatisticsView(self.store, self.guild_id, self.owner_id), ephemeral=True)

    @discord.ui.button(label='Manutenção e backup', emoji='🛠️', style=discord.ButtonStyle.secondary, row=1)
    async def maintenance(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .maintenance_panel import MaintenanceView
        await interaction.response.send_message(
            '**Manutenção do Reaction Roles:** diagnóstico, exportação e restauração de JSON.',
            view=MaintenanceView(self.store, self.guild_id, self.owner_id), ephemeral=True)

    @discord.ui.button(label='Fechar', emoji='🔒', style=discord.ButtonStyle.danger, row=1)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self):
        self.stop()

