"""Interface administrativa para alternar entre reações, botões e menus."""
import discord
from .permissions import admin_only
from ..services.panels import panel_embed
from ..services.buttons import make_button_view
from ..services.select_menus import build_select_view

MODES = ("reactions", "buttons", "select")

def panel_view(bot, store, guild_id, panel):
    mode = panel.get("interface", "reactions")
    if mode == "buttons":
        return make_button_view(bot, store, guild_id, panel)
    if mode == "select":
        return build_select_view(bot, store, guild_id, panel)
    return None

class InterfacePanelSelect(discord.ui.Select):
    def __init__(self, panels, mode):
        super().__init__(placeholder=f"Escolha painel para {mode}",
            options=[discord.SelectOption(label=p["title"][:100], value=pid)
                     for pid, p in list(panels.items())[:25]])
        self.mode = mode

    async def callback(self, interaction):
        parent = self.view
        if not await admin_only(interaction, parent.guild_id, parent.owner_id):
            return
        data = await parent.store.get(parent.guild_id)
        panel = data.get("panels", {}).get(self.values[0])
        if panel is None:
            return await interaction.response.send_message("Painel não encontrado.", ephemeral=True)
        if self.mode != "reactions" and not panel.get("roles"):
            return await interaction.response.send_message("Configure emojis e cargos antes.", ephemeral=True)
        if self.mode != "reactions" and panel.get("reversed"):
            return await interaction.response.send_message("O modo Reversed exige reações.", ephemeral=True)
        await interaction.response.defer(thinking=True, ephemeral=True)
        updated = {**panel, "interface": self.mode}
        message = None
        if panel.get("channel_id") and panel.get("message_id"):
            channel = interaction.guild.get_channel(int(panel["channel_id"]))
            if channel is None:
                return await interaction.followup.send("Canal da publicação não encontrado.", ephemeral=True)
            try:
                message = await channel.fetch_message(int(panel["message_id"]))
                await message.edit(embed=panel_embed(discord, updated),
                                   view=panel_view(interaction.client, parent.store, parent.guild_id, updated))
                if self.mode == "reactions":
                    from ..services.reactions import sync_message
                    await sync_message(message, updated)
            except (discord.HTTPException, discord.Forbidden):
                return await interaction.followup.send("Falha ao atualizar a publicação.", ephemeral=True)
        def update(data):
            current = data.get("panels", {}).get(self.values[0])
            if current is None:
                raise ValueError("Painel removido.")
            current["interface"] = self.mode
        await parent.store.mutate(parent.guild_id, update)
        if message is not None and self.mode != "reactions":
            interaction.client.add_view(
                panel_view(interaction.client, parent.store, parent.guild_id, updated),
                message_id=message.id)
        await interaction.followup.send(f"Interface alterada para **{self.mode}**.", ephemeral=True)

class InterfaceModeView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panels):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id
        self.add_item(discord.ui.Select(
            placeholder="Escolha o tipo de interface",
            options=[discord.SelectOption(label=label, value=value) for label, value in
                     (("Reações", "reactions"), ("Botões", "buttons"), ("Menu de seleção", "select"))],
            custom_id="kingplus:rr:admin:interface"))
        self.children[0].callback = self.choose_mode
        self.panels = panels

    async def choose_mode(self, interaction):
        if not await admin_only(interaction, self.guild_id, self.owner_id):
            return
        mode = interaction.data["values"][0]
        await interaction.response.send_message(
            "Selecione o painel:", view=PanelChoiceView(self.store, self.guild_id,
                                                       self.owner_id, self.panels, mode), ephemeral=True)

class PanelChoiceView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panels, mode):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id
        self.add_item(InterfacePanelSelect(panels, mode))
