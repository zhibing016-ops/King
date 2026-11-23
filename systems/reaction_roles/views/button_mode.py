import discord
from .permissions import admin_only
from ..services.buttons import make_button_view
from ..services.panels import panel_embed

class ButtonPanelSelect(discord.ui.Select):
    def __init__(self, panels):
        super().__init__(placeholder="Escolha um painel para alternar interface",
                         options=[discord.SelectOption(label=p["title"][:100], value=pid)
                                  for pid,p in list(panels.items())[:25]])
    async def callback(self, interaction):
        parent = self.view
        if not await admin_only(interaction, parent.guild_id, parent.owner_id):
            return
        pid = self.values[0]
        data = await parent.store.get(parent.guild_id)
        panel = data["panels"].get(pid)
        if not panel:
            return await interaction.response.send_message("Painel não encontrado.", ephemeral=True)
        new_mode = "reactions" if panel.get("interface") == "buttons" else "buttons"
        if new_mode == "buttons" and panel.get("reversed"):
            return await interaction.response.send_message("Reversed não é compatível com botões.", ephemeral=True)
        if new_mode == "buttons" and not panel.get("roles"):
            return await interaction.response.send_message("Associe emojis e cargos antes.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        # Validate existing published message before committing the new interface.
        message = None
        if panel.get("message_id") and panel.get("channel_id"):
            channel = interaction.guild.get_channel(int(panel["channel_id"]))
            if channel is None:
                return await interaction.followup.send("Canal não encontrado.", ephemeral=True)
            try:
                message = await channel.fetch_message(int(panel["message_id"]))
                view = (make_button_view(parent.bot, parent.store, parent.guild_id,
                                         {**panel, "interface": new_mode}) if new_mode == "buttons" else None)
                await message.edit(embed=panel_embed(discord, panel), view=view)
            except discord.HTTPException:
                return await interaction.followup.send("Não foi possível atualizar a mensagem publicada.", ephemeral=True)
        def mutate(data):
            current = data.get("panels", {}).get(pid)
            if current is None:
                raise ValueError("Painel removido.")
            current["interface"] = new_mode
        await parent.store.mutate(parent.guild_id, mutate)
        if message and new_mode == "buttons":
            parent.bot.add_view(make_button_view(parent.bot, parent.store, parent.guild_id,
                                                 {**panel, "interface": new_mode}), message_id=message.id)
        await interaction.followup.send(f"Interface alterada para **{new_mode}**." +
                                         (" Publique o painel para ativá-la." if not message else ""),
                                         ephemeral=True)

class ButtonModeView(discord.ui.View):
    def __init__(self, bot, store, guild_id, owner_id, panels):
        super().__init__(timeout=180)
        self.bot, self.store, self.guild_id, self.owner_id = bot, store, guild_id, owner_id
        self.add_item(ButtonPanelSelect(panels))
