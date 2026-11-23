"""Painel de seleção dos modos Reversed e Binding."""
import discord
from .permissions import admin_only
from ..services.modes import panel_mode, set_mode

class ModePanelSelect(discord.ui.Select):
    def __init__(self, panels, mode):
        self.mode = mode
        super().__init__(placeholder=f"Selecione um painel para {mode}", min_values=1, max_values=1,
            options=[discord.SelectOption(label=p.get("title", "Painel")[:100], value=pid,
                description=f"Modo atual: {panel_mode(p)}") for pid, p in list(panels.items())[:25]])

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not await admin_only(interaction, view.guild_id, view.owner_id):
            return
        pid = self.values[0]
        current = (await view.store.get(view.guild_id)).get("panels", {}).get(pid)
        if current is None:
            await interaction.response.send_message("❌ Painel não encontrado.", ephemeral=True)
            return
        new_mode = "normal" if panel_mode(current) == self.mode else self.mode
        try:
            panel = await set_mode(view.store, view.guild_id, pid, new_mode)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=f"✅ Modo **{panel_mode(panel).upper()}** salvo no painel **{discord.utils.escape_markdown(panel['title'])}**.",
            view=None)

class AdvancedModeView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panels, mode):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id
        self.add_item(ModePanelSelect(panels, mode))

    async def interaction_check(self, interaction):
        return await admin_only(interaction, self.guild_id, self.owner_id)
