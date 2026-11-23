"""Painel único /reactionroles, com navegação por botões."""
import discord
from .permissions import admin_only


class ReactionRolesDashboard(discord.ui.View):
    def __init__(self, store, guild_id, owner_id):
        super().__init__(timeout=300)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id

    async def interaction_check(self, interaction):
        return await admin_only(interaction, self.guild_id, self.owner_id)

    async def make_embed(self):
        data = await self.store.get(self.guild_id)
        active = bool(data.get('enabled', False))
        embed = discord.Embed(
            title='👑 KING PLUS — Reaction Roles',
            description='Gerenciamento completo de cargos automáticos\n\n'
                        'Configure painéis, interfaces, cargos, permissões e auditoria.',
            color=discord.Color.green() if active else discord.Color.blurple())
        embed.add_field(name='Sistema', value='🟢 Ativo' if active else '🔴 Desativado')
        embed.add_field(name='Painéis', value=str(len(data.get('panels', {}))))
        embed.set_footer(text='🗄️ Armazenamento: JSON • 🔐 Admin • 16 fases')
        return embed

    @discord.ui.button(label='Criar Painel', emoji='🧩', style=discord.ButtonStyle.primary, row=0)
    async def create_panel(self, interaction, button):
        from .panels import PanelManager
        view = PanelManager(self.store, self.guild_id, self.owner_id)
        await interaction.response.send_message(embed=await view.make_embed(), view=view, ephemeral=True)

    @discord.ui.button(label='Cargos e Emojis', emoji='🎭', row=0)
    async def mappings(self, interaction, button):
        from .role_mappings import MappingManager
        await interaction.response.send_message('Configure associações entre cargos e emojis:',
            view=MappingManager(self.store, self.guild_id, self.owner_id), ephemeral=True)

    @discord.ui.button(label='Interfaces', emoji='🔘', row=1)
    async def interfaces(self, interaction, button):
        from .interface_mode import InterfaceModeView
        panels = (await self.store.get(self.guild_id)).get('panels', {})
        if not panels:
            return await interaction.response.send_message('Crie um painel primeiro.', ephemeral=True)
        await interaction.response.send_message('Reações, botões e menus de seleção:',
            view=InterfaceModeView(self.store, self.guild_id, self.owner_id, panels), ephemeral=True)

    @discord.ui.button(label='Permissões', emoji='🛡️', row=1)
    async def access(self, interaction, button):
        from .access_control import AccessManager
        panels = (await self.store.get(self.guild_id)).get('panels', {})
        if not panels:
            return await interaction.response.send_message('Crie um painel primeiro.', ephemeral=True)
        await interaction.response.send_message('Restrições e requisitos por painel:',
            view=AccessManager(self.store, self.guild_id, self.owner_id, panels), ephemeral=True)

    @discord.ui.button(label='Personalização', emoji='🎨', row=2)
    async def appearance(self, interaction, button):
        from .customization import CustomizeManager
        panels = (await self.store.get(self.guild_id)).get('panels', {})
        if not panels:
            return await interaction.response.send_message('Crie um painel primeiro.', ephemeral=True)
        await interaction.response.send_message('Edite embeds, imagens, cores e rodapés:',
            view=CustomizeManager(self.store, self.guild_id, self.owner_id, panels), ephemeral=True)

    @discord.ui.button(label='Configurações', emoji='⚙️', row=2)
    async def settings(self, interaction, button):
        from .admin_panel import AdminPanel
        view = AdminPanel(self.store, self.guild_id, self.owner_id)
        await interaction.response.send_message(embed=await view.make_embed(), view=view, ephemeral=True)

    @discord.ui.button(label='Logs', emoji='📋', row=3)
    async def logs(self, interaction, button):
        from .audit_panel import AuditView
        await interaction.response.send_message('Logs e auditoria:',
            view=AuditView(self.store, self.guild_id, self.owner_id), ephemeral=True)

    @discord.ui.button(label='Estatísticas', emoji='📊', row=3)
    async def statistics(self, interaction, button):
        from .statistics_panel import StatisticsView
        await interaction.response.send_message('Selecione o período do relatório:',
            view=StatisticsView(self.store, self.guild_id, self.owner_id), ephemeral=True)

    @discord.ui.button(label='Manutenção', emoji='🛠️', row=4)
    async def maintenance(self, interaction, button):
        from .maintenance_panel import MaintenanceView
        await interaction.response.send_message('Diagnóstico, backup e restauração:',
            view=MaintenanceView(self.store, self.guild_id, self.owner_id), ephemeral=True)

    @discord.ui.button(label='Fechar', emoji='🔒', style=discord.ButtonStyle.danger, row=4)
    async def close(self, interaction, button):
        self.stop()
        await interaction.response.edit_message(content='Painel encerrado.', embed=None, view=None)
