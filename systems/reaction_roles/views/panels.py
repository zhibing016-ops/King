"""Painel de gerenciamento com modal, seleção de canal e prévia."""
import discord
from ..services.panels import create_panel, delete_panel, panel_embed, parse_color, save_publication
from ..services.reactions import sync_message
from .interface_mode import panel_view

from .permissions import admin_only

class CreatePanelModal(discord.ui.Modal, title='Criar painel • KING PLUS'):
    panel_title = discord.ui.TextInput(label='Título', max_length=256, placeholder='Escolha seus cargos')
    description = discord.ui.TextInput(label='Descrição', style=discord.TextStyle.paragraph,
                                      max_length=4000, placeholder='Selecione os cargos disponíveis...')
    color = discord.ui.TextInput(label='Cor hexadecimal', default='#5865F2', max_length=7)

    def __init__(self, store, guild_id, owner_id):
        super().__init__(timeout=300)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id

    async def on_submit(self, interaction):
        if not await admin_only(interaction, self.guild_id, self.owner_id):
            return
        try:
            color = parse_color(str(self.color))
            panel = await create_panel(self.store, self.guild_id, str(self.panel_title), str(self.description), color)
        except ValueError as exc:
            await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
            return
        await interaction.response.send_message(
            f'✅ Painel criado! ID: `{panel["id"]}`. Use **Publicar** para escolher um canal.',
            embed=panel_embed(discord, panel), ephemeral=True)

class PanelSelector(discord.ui.Select):
    def __init__(self, panels, action):
        options = [discord.SelectOption(label=p['title'][:100], value=pid,
                    description=f'ID: {pid}'[:100]) for pid, p in list(panels.items())[:25]]
        super().__init__(placeholder='Escolha o painel', options=options)
        self.action = action

    async def callback(self, interaction):
        parent = self.view
        if not await admin_only(interaction, parent.guild_id, parent.owner_id):
            return
        panel_id = self.values[0]
        data = await parent.store.get(parent.guild_id)
        panel = data.get('panels', {}).get(panel_id)
        if not panel:
            await interaction.response.send_message('❌ Painel não encontrado.', ephemeral=True)
            return
        if self.action == 'preview':
            await interaction.response.send_message(embed=panel_embed(discord, panel), ephemeral=True)
        elif self.action == 'publish':
            await interaction.response.send_message('Escolha o canal para publicar:',
                view=PublishChannelView(parent.store, parent.guild_id, parent.owner_id, panel_id), ephemeral=True)
        elif self.action == 'delete':
            await interaction.response.send_message(f'Confirma excluir `{panel["title"]}` do JSON?',
                view=ConfirmDeleteView(parent.store, parent.guild_id, parent.owner_id, panel_id), ephemeral=True)

class SelectPanelView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panels, action):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id
        self.add_item(PanelSelector(panels, action))

class ChannelPicker(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder='Canal de publicação', channel_types=[discord.ChannelType.text])

    async def callback(self, interaction):
        parent = self.view
        if not await admin_only(interaction, parent.guild_id, parent.owner_id):
            return
        channel = self.values[0]
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message('❌ Servidor indisponível.', ephemeral=True)
            return
        channel = guild.get_channel(channel.id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message('❌ Escolha um canal de texto acessível.', ephemeral=True)
            return
        me = guild.me
        perms = channel.permissions_for(me)
        if not (perms.view_channel and perms.send_messages and perms.embed_links and perms.read_message_history):
            await interaction.response.send_message('❌ O bot precisa de Ver Canal, Enviar Mensagens, Inserir Links e Ler Histórico.', ephemeral=True)
            return
        if (await parent.store.get(parent.guild_id)).get("panels", {}).get(parent.panel_id, {}).get("interface", "reactions") == "reactions" and not perms.add_reactions:
            await interaction.response.send_message('❌ O bot precisa de Ver Canal, Enviar Mensagens, Inserir Links, Adicionar Reações e Ler Histórico.', ephemeral=True)
            return
        data = await parent.store.get(parent.guild_id)
        panel = data.get('panels', {}).get(parent.panel_id)
        if not panel:
            await interaction.response.send_message('❌ Painel removido.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        interface = panel.get("interface", "reactions")
        if interface in ("buttons", "select") and not panel.get("roles"):
            return await interaction.followup.send("Configure emojis e cargos antes de publicar.", ephemeral=True)
        try:
            view = panel_view(interaction.client, parent.store, parent.guild_id, panel)
            message = await channel.send(embed=panel_embed(discord, panel), view=view)
            errors = await sync_message(message, panel) if interface == "reactions" else []
        except discord.HTTPException:
            await interaction.followup.send('❌ Falha ao publicar no canal.', ephemeral=True)
            return
        try:
            await save_publication(parent.store, parent.guild_id, parent.panel_id, channel.id, message.id)
        except Exception:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            await interaction.followup.send('❌ Falha ao salvar publicação. Confira os logs.', ephemeral=True)
            raise
        if interface in ("buttons", "select"):
            interaction.client.add_view(panel_view(interaction.client, parent.store, parent.guild_id, panel),
                                        message_id=message.id)
        await interaction.followup.send(f'✅ Painel publicado em {channel.mention}! Mensagem: `{message.id}`' + ('\n⚠️ Alguns emojis não puderam ser adicionados: ' + ', '.join(errors) if errors else ''), ephemeral=True)

class PublishChannelView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panel_id):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id, self.panel_id = store, guild_id, owner_id, panel_id
        self.add_item(ChannelPicker())

class ConfirmDeleteView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panel_id):
        super().__init__(timeout=120)
        self.store, self.guild_id, self.owner_id, self.panel_id = store, guild_id, owner_id, panel_id

    @discord.ui.button(label='Confirmar exclusão', style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        if not await admin_only(interaction, self.guild_id, self.owner_id):
            return
        try:
            await delete_panel(self.store, self.guild_id, self.panel_id)
        except ValueError as exc:
            await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
            return
        await interaction.response.edit_message(content='✅ Registro excluído do JSON. A mensagem publicada, se existir, permanece no canal.', view=None)
        self.stop()

class PanelManager(discord.ui.View):
    def __init__(self, store, guild_id, owner_id):
        super().__init__(timeout=300)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id

    async def interaction_check(self, interaction):
        return await admin_only(interaction, self.guild_id, self.owner_id)

    async def make_embed(self):
        data = await self.store.get(self.guild_id)
        panels = data.get('panels', {})
        embed = discord.Embed(title='🧩 KING PLUS • Gerenciar painéis', color=discord.Color.blurple(),
                              description=f'Painéis cadastrados: **{len(panels)}/25**\nEmojis e cargos configuráveis. Atribuição automática ativa nas mensagens publicadas.')
        for pid, p in list(panels.items())[:15]:
            embed.add_field(name=p['title'][:256], value=f'ID `{pid}` • '+('Publicado' if p.get('message_id') else 'Rascunho'), inline=False)
        return embed

    async def choose(self, interaction, action):
        panels = (await self.store.get(self.guild_id)).get('panels', {})
        if not panels:
            await interaction.response.send_message('Nenhum painel cadastrado. Clique em Criar.', ephemeral=True)
            return
        await interaction.response.send_message('Selecione o painel:',
            view=SelectPanelView(self.store, self.guild_id, self.owner_id, panels, action), ephemeral=True)

    @discord.ui.button(label='Criar', emoji='➕', style=discord.ButtonStyle.success, row=0)
    async def create(self, interaction, button):
        await interaction.response.send_modal(CreatePanelModal(self.store, self.guild_id, self.owner_id))

    @discord.ui.button(label='Publicar', emoji='📤', style=discord.ButtonStyle.primary, row=0)
    async def publish(self, interaction, button):
        await self.choose(interaction, 'publish')

    @discord.ui.button(label='Prévia', emoji='👁️', style=discord.ButtonStyle.secondary, row=0)
    async def preview(self, interaction, button):
        await self.choose(interaction, 'preview')

    @discord.ui.button(label='Excluir', emoji='🗑️', style=discord.ButtonStyle.danger, row=1)
    async def delete(self, interaction, button):
        await self.choose(interaction, 'delete')

    @discord.ui.button(label='Atualizar', emoji='🔄', style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction, button):
        await interaction.response.edit_message(embed=await self.make_embed(), view=self)
