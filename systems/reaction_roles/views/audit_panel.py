"""Configuração do canal de logs e histórico via Discord."""
import discord
from .permissions import admin_only
from ..services.audit import audit_settings, set_audit_channel, record_audit

class AuditChannelPicker(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder='Selecione o canal de logs', channel_types=[discord.ChannelType.text], min_values=1, max_values=1)

    async def callback(self, interaction):
        parent = self.view
        if not await admin_only(interaction, parent.guild_id, parent.owner_id):
            return
        channel = self.values[0]
        resolved = interaction.guild.get_channel(channel.id)
        if resolved is None:
            return await interaction.response.send_message('Canal não encontrado.', ephemeral=True)
        me = interaction.guild.me
        perms = resolved.permissions_for(me)
        if not (perms.view_channel and perms.send_messages):
            return await interaction.response.send_message('Preciso de Ver Canal e Enviar Mensagens.', ephemeral=True)
        await set_audit_channel(parent.store, parent.guild_id, resolved.id)
        await interaction.response.send_message(f'✅ Logs configurados em {resolved.mention}.', ephemeral=True)
        await record_audit(interaction.client, parent.store, parent.guild_id, 'config',
                           member_id=interaction.user.id, source='admin', note='Canal de logs configurado')

class AuditView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id
        self.add_item(AuditChannelPicker())

    async def interaction_check(self, interaction):
        return await admin_only(interaction, self.guild_id, self.owner_id)

    @discord.ui.button(label='Histórico recente', emoji='📋', row=1)
    async def history(self, interaction, button):
        entries = audit_settings(await self.store.get(self.guild_id))['history'][-10:]
        if not entries:
            return await interaction.response.send_message('Nenhum evento registrado.', ephemeral=True)
        lines = [f'`{x["at"][:19]}` **{x["event"]}** • usuário `{x["member_id"]}` • cargo `{x["role_id"]}`' for x in reversed(entries)]
        await interaction.response.send_message('\n'.join(lines)[:1900], ephemeral=True)

    @discord.ui.button(label='Desativar canal', emoji='🔕', row=1)
    async def clear(self, interaction, button):
        await set_audit_channel(self.store, self.guild_id, None)
        await interaction.response.send_message('Canal de logs desativado; histórico JSON continua ativo.', ephemeral=True)
