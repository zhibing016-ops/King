"""Painel administrativo para ativar/desativar modo Unique."""
import discord
from .permissions import admin_only
from ..services.unique import set_unique

class UniquePanelSelect(discord.ui.Select):
    def __init__(self, panels):
        super().__init__(placeholder='Escolha o painel para alternar Unique', min_values=1, max_values=1,
                         options=[discord.SelectOption(label=p['title'][:100], value=pid,
                                  description='Unique ativo' if p.get('unique') else 'Unique desativado')
                                  for pid, p in list(panels.items())[:25]])

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not await admin_only(interaction, view.guild_id, view.owner_id):
            return
        pid = self.values[0]
        panel = (await view.store.get(view.guild_id)).get('panels', {}).get(pid)
        if not panel:
            await interaction.response.send_message('❌ Painel não encontrado.', ephemeral=True)
            return
        try:
            updated = await set_unique(view.store, view.guild_id, pid, not panel.get('unique', False))
        except ValueError as exc:
            await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
            return
        state = 'ATIVADO' if updated['unique'] else 'DESATIVADO'
        await interaction.response.edit_message(content=f'✅ Modo Unique **{state}** no painel **{discord.utils.escape_markdown(updated["title"])}**. A configuração foi salva em JSON.', view=None)

class UniqueModeView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panels):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id
        self.add_item(UniquePanelSelect(panels))

    async def interaction_check(self, interaction):
        return await admin_only(interaction, self.guild_id, self.owner_id)
