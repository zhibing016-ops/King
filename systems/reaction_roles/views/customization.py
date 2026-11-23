import discord
from .permissions import admin_only
from ..services.panels import validate_customization, save_customization, panel_embed

async def commit(interaction, store, guild_id, panel_id, values):
    await interaction.response.defer(ephemeral=True, thinking=True)
    panel = (await store.get(guild_id)).get('panels', {}).get(panel_id)
    if not panel:
        return await interaction.followup.send('Painel não encontrado.', ephemeral=True)
    updated = {**panel, **values}
    warning = ''
    if panel.get('channel_id') and panel.get('message_id'):
        channel = interaction.guild.get_channel(int(panel['channel_id']))
        if channel:
            try:
                message = await channel.fetch_message(int(panel['message_id']))
                await message.edit(embed=panel_embed(discord, updated))
            except (discord.HTTPException, discord.Forbidden):
                warning = ' Mensagem pública não atualizada; confira permissões.'
        else:
            warning = ' Canal não encontrado; publique novamente.'
    await save_customization(store, guild_id, panel_id, values)
    await interaction.followup.send('✅ Personalização salva em JSON.' + warning,
                                    embed=panel_embed(discord, updated), ephemeral=True)

class TextModal(discord.ui.Modal, title='KING PLUS • Texto e cor'):
    heading = discord.ui.TextInput(label='Título', max_length=256)
    body = discord.ui.TextInput(label='Descrição', style=discord.TextStyle.paragraph, max_length=4000)
    color = discord.ui.TextInput(label='Cor hexadecimal', max_length=7)
    footer = discord.ui.TextInput(label='Rodapé (opcional)', required=False, max_length=2048)
    def __init__(self, store, guild_id, owner_id, panel):
        super().__init__()
        self.store, self.guild_id, self.owner_id, self.pid = store, guild_id, owner_id, panel['id']
        self.heading.default, self.body.default = panel['title'], panel['description']
        self.color.default = f"#{panel['color']:06X}"
        self.footer.default = panel.get('footer_text', '')
    async def on_submit(self, interaction):
        if not await admin_only(interaction, self.guild_id, self.owner_id): return
        panel = (await self.store.get(self.guild_id)).get('panels', {}).get(self.pid)
        if not panel: return await interaction.response.send_message('Painel removido.', ephemeral=True)
        try:
            values = validate_customization(str(self.heading), str(self.body), str(self.color),
                panel.get('thumbnail_url', ''), panel.get('image_url', ''), str(self.footer))
        except ValueError as exc:
            return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
        await commit(interaction, self.store, self.guild_id, self.pid, values)

class ImagesModal(discord.ui.Modal, title='KING PLUS • Imagens'):
    thumbnail = discord.ui.TextInput(label='URL HTTPS da thumbnail', required=False, max_length=2000)
    image = discord.ui.TextInput(label='URL HTTPS da imagem principal', required=False, max_length=2000)
    def __init__(self, store, guild_id, owner_id, panel):
        super().__init__()
        self.store, self.guild_id, self.owner_id, self.pid = store, guild_id, owner_id, panel['id']
        self.thumbnail.default, self.image.default = panel.get('thumbnail_url',''), panel.get('image_url','')
    async def on_submit(self, interaction):
        if not await admin_only(interaction, self.guild_id, self.owner_id): return
        panel = (await self.store.get(self.guild_id)).get('panels', {}).get(self.pid)
        if not panel: return await interaction.response.send_message('Painel removido.', ephemeral=True)
        try:
            values = validate_customization(panel['title'], panel['description'], f"#{panel['color']:06X}",
                str(self.thumbnail), str(self.image), panel.get('footer_text',''))
        except ValueError as exc:
            return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
        await commit(interaction, self.store, self.guild_id, self.pid, values)

class Actions(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, pid):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id, self.pid = store, guild_id, owner_id, pid
    async def interaction_check(self, interaction):
        return await admin_only(interaction, self.guild_id, self.owner_id)
    async def get_panel(self):
        return (await self.store.get(self.guild_id)).get('panels', {}).get(self.pid)
    @discord.ui.button(label='Texto e cor', emoji='🎨', style=discord.ButtonStyle.primary)
    async def text(self, interaction, button):
        panel = await self.get_panel()
        if not panel: return await interaction.response.send_message('Painel removido.', ephemeral=True)
        await interaction.response.send_modal(TextModal(self.store, self.guild_id, self.owner_id, panel))
    @discord.ui.button(label='Imagens', emoji='🖼️', style=discord.ButtonStyle.secondary)
    async def images(self, interaction, button):
        panel = await self.get_panel()
        if not panel: return await interaction.response.send_message('Painel removido.', ephemeral=True)
        await interaction.response.send_modal(ImagesModal(self.store, self.guild_id, self.owner_id, panel))
    @discord.ui.button(label='Prévia', emoji='👁️', style=discord.ButtonStyle.secondary)
    async def preview(self, interaction, button):
        panel = await self.get_panel()
        if not panel: return await interaction.response.send_message('Painel removido.', ephemeral=True)
        await interaction.response.send_message(embed=panel_embed(discord, panel), ephemeral=True)

class ChoosePanel(discord.ui.Select):
    def __init__(self, panels):
        super().__init__(placeholder='Escolha o painel', options=[discord.SelectOption(label=p['title'][:100], value=pid) for pid,p in list(panels.items())[:25]])
    async def callback(self, interaction):
        view = self.view
        if not await admin_only(interaction, view.guild_id, view.owner_id): return
        await interaction.response.send_message('Personalize o embed:', view=Actions(view.store, view.guild_id, view.owner_id, self.values[0]), ephemeral=True)

class CustomizeManager(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panels):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id
        self.add_item(ChoosePanel(panels))
