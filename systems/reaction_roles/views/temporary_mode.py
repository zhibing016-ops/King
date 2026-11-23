"""Painel para ativar/desativar cargos temporários por painel."""
import discord
from .permissions import admin_only
from ..services.temporary import configure_temporary

class DurationModal(discord.ui.Modal, title='KING PLUS • Duração temporária'):
    minutes = discord.ui.TextInput(label='Duração em minutos (1 a 43200)', placeholder='60', max_length=5)
    def __init__(self, view, panel_id):
        super().__init__()
        self.owner_view, self.panel_id = view, panel_id

    async def on_submit(self, interaction):
        if not await admin_only(interaction, self.owner_view.guild_id, self.owner_view.owner_id):
            return
        try:
            seconds = int(str(self.minutes.value).strip()) * 60
            await configure_temporary(self.owner_view.store, self.owner_view.guild_id, self.panel_id, seconds)
        except (ValueError, TypeError) as exc:
            await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
            return
        await interaction.response.send_message(f'✅ Cargo temporário configurado por **{seconds // 60} minutos**. A duração começa quando o cargo é concedido.', ephemeral=True)

class TemporaryPanelSelect(discord.ui.Select):
    def __init__(self, panels):
        options = [discord.SelectOption(label=p.get('title','Painel')[:100], value=pid,
            description=('Temporário: '+str(p['temporary_seconds']//60)+' min') if p.get('temporary_seconds') else 'Desativado')
            for pid,p in list(panels.items())[:25]]
        super().__init__(placeholder='Selecione o painel', options=options)

    async def callback(self, interaction):
        view = self.view
        if not await admin_only(interaction, view.guild_id, view.owner_id):
            return
        view.selected_panel = self.values[0]
        await interaction.response.send_message('Painel selecionado. Escolha **Configurar duração** ou **Desativar**.', ephemeral=True)

class TemporaryModeView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panels):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id
        self.selected_panel = None
        self.add_item(TemporaryPanelSelect(panels))

    async def interaction_check(self, interaction):
        return await admin_only(interaction, self.guild_id, self.owner_id)

    @discord.ui.button(label='Configurar duração', emoji='⏱️', style=discord.ButtonStyle.primary)
    async def configure(self, interaction, button):
        if not self.selected_panel:
            await interaction.response.send_message('Selecione um painel primeiro.', ephemeral=True)
            return
        await interaction.response.send_modal(DurationModal(self, self.selected_panel))

    @discord.ui.button(label='Desativar temporário', emoji='🛑', style=discord.ButtonStyle.danger)
    async def disable(self, interaction, button):
        if not self.selected_panel:
            await interaction.response.send_message('Selecione um painel primeiro.', ephemeral=True)
            return
        await configure_temporary(self.store, self.guild_id, self.selected_panel, None)
        await interaction.response.send_message('✅ Modo temporário desativado. Cargos já concedidos ainda expirarão no prazo registrado.', ephemeral=True)
