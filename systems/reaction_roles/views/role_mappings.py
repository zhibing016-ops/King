"""Interface administrativa de associações emoji/cargo."""
import discord
from .permissions import admin_only
from ..services.roles import add_mapping, remove_mapping, validate_emoji
from ..services.reactions import sync_message


async def refresh_published(interaction, store, guild_id, panel_id):
    """Sincroniza uma mensagem publicada quando associação é alterada."""
    panel = (await store.get(guild_id)).get('panels', {}).get(panel_id)
    if not panel or not panel.get('message_id'):
        return 'Painel ainda não publicado.'
    guild = interaction.guild
    channel = guild.get_channel(int(panel['channel_id'])) if guild else None
    if not isinstance(channel, discord.TextChannel):
        return 'Canal não acessível. Publique o painel novamente.'
    try:
        message = await channel.fetch_message(int(panel['message_id']))
        # Remove reações antigas do próprio bot quando não estão mais cadastradas.
        wanted = {str(e) for e in panel.get('roles', {})}
        for reaction in message.reactions:
            if reaction.me and str(reaction.emoji) not in wanted:
                await reaction.remove(guild.me)
        errors = await sync_message(message, panel)
        return 'Mensagem atualizada.' + (f' Falha em {len(errors)} emoji(s).' if errors else '')
    except (discord.HTTPException, discord.Forbidden, AttributeError):
        return 'Não foi possível atualizar a mensagem; confira permissões ou publique novamente.'

class AddEmojiModal(discord.ui.Modal, title='Associar emoji ao cargo'):
    emoji = discord.ui.TextInput(label='Emoji Unicode ou personalizado', max_length=64, placeholder='🎮')
    def __init__(self, store, guild_id, owner_id, panel_id, role_id):
        super().__init__(timeout=300)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id
        self.panel_id, self.role_id = panel_id, role_id
    async def on_submit(self, interaction):
        if not await admin_only(interaction, self.guild_id, self.owner_id):
            return
        try:
            emoji = validate_emoji(str(self.emoji))
            await add_mapping(self.store, self.guild_id, self.panel_id, emoji, self.role_id)
        except ValueError as exc:
            await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
            return
        result = await refresh_published(interaction, self.store, self.guild_id, self.panel_id)
        await interaction.response.send_message(f'✅ {emoji} associado a <@&{self.role_id}>. {result}', ephemeral=True)

class RolePicker(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder='Escolha o cargo', min_values=1, max_values=1)
    async def callback(self, interaction):
        view = self.view
        if not await admin_only(interaction, view.guild_id, view.owner_id):
            return
        guild = interaction.guild
        role = guild.get_role(self.values[0].id) if guild else None
        me = guild.me if guild else None
        if not role or not me or role.is_default() or role.managed or role >= me.top_role or not me.guild_permissions.manage_roles:
            await interaction.response.send_message('❌ Cargo não gerenciável pelo bot. Verifique a hierarquia e a permissão Gerenciar Cargos.', ephemeral=True)
            return
        await interaction.response.send_modal(AddEmojiModal(view.store, view.guild_id, view.owner_id, view.panel_id, role.id))

class AddMappingView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panel_id):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id, self.panel_id = store, guild_id, owner_id, panel_id
        self.add_item(RolePicker())

class RemoveMappingSelect(discord.ui.Select):
    def __init__(self, roles):
        super().__init__(placeholder='Associação para remover', options=[discord.SelectOption(label=f'{emoji} → {rid}'[:100], value=emoji) for emoji, rid in list(roles.items())[:20]])
    async def callback(self, interaction):
        view = self.view
        if not await admin_only(interaction, view.guild_id, view.owner_id):
            return
        try:
            await remove_mapping(view.store, view.guild_id, view.panel_id, self.values[0])
        except ValueError as exc:
            await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
            return
        result = await refresh_published(interaction, view.store, view.guild_id, view.panel_id)
        await interaction.response.edit_message(content=f'✅ Associação removida do JSON. {result}', view=None)

class RemoveMappingView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panel_id, roles):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id, self.panel_id = store, guild_id, owner_id, panel_id
        self.add_item(RemoveMappingSelect(roles))

class MappingPanelSelect(discord.ui.Select):
    def __init__(self, panels, action):
        super().__init__(placeholder='Selecione o painel', options=[discord.SelectOption(label=p['title'][:100], value=pid) for pid,p in list(panels.items())[:25]])
        self.action = action
    async def callback(self, interaction):
        view = self.view
        if not await admin_only(interaction, view.guild_id, view.owner_id):
            return
        panel_id = self.values[0]
        panel = (await view.store.get(view.guild_id)).get('panels', {}).get(panel_id)
        if not panel:
            await interaction.response.send_message('❌ Painel inexistente.', ephemeral=True)
            return
        roles = panel.get('roles', {})
        if self.action == 'add':
            await interaction.response.send_message('Selecione um cargo gerenciável:', view=AddMappingView(view.store, view.guild_id, view.owner_id, panel_id), ephemeral=True)
        elif self.action == 'remove':
            if not roles:
                await interaction.response.send_message('Nenhuma associação neste painel.', ephemeral=True)
                return
            await interaction.response.send_message('Selecione a associação:', view=RemoveMappingView(view.store, view.guild_id, view.owner_id, panel_id, roles), ephemeral=True)
        else:
            lines = [f'{emoji} → <@&{rid}>' for emoji,rid in roles.items()]
            await interaction.response.send_message('**Associações:**\n'+('\n'.join(lines) if lines else 'Nenhuma associação.'), ephemeral=True)

class MappingSelectView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, panels, action):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id
        self.add_item(MappingPanelSelect(panels, action))

class MappingManager(discord.ui.View):
    def __init__(self, store, guild_id, owner_id):
        super().__init__(timeout=300)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id
    async def interaction_check(self, interaction):
        return await admin_only(interaction, self.guild_id, self.owner_id)
    async def choose(self, interaction, action):
        panels = (await self.store.get(self.guild_id)).get('panels', {})
        if not panels:
            await interaction.response.send_message('Crie um painel antes de configurar emojis.', ephemeral=True)
            return
        await interaction.response.send_message('Selecione o painel:', view=MappingSelectView(self.store, self.guild_id, self.owner_id, panels, action), ephemeral=True)
    @discord.ui.button(label='Associar emoji + cargo', emoji='➕', style=discord.ButtonStyle.success)
    async def add(self, interaction, button):
        await self.choose(interaction, 'add')
    @discord.ui.button(label='Remover associação', emoji='🗑️', style=discord.ButtonStyle.danger)
    async def remove(self, interaction, button):
        await self.choose(interaction, 'remove')
    @discord.ui.button(label='Listar associações', emoji='📋', style=discord.ButtonStyle.secondary)
    async def list_mappings(self, interaction, button):
        await self.choose(interaction, 'list')
