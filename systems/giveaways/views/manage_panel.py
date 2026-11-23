import discord
from datetime import datetime, timezone
from .admin_panel import is_admin


class ManageSelect(discord.ui.Select):
    def __init__(self, cog, records):
        self.cog = cog
        options = [discord.SelectOption(label=str(g.get('prize', 'Prêmio'))[:95], value=str(g['message_id']),
                   description=f"Canal {g.get('channel_id')} | {len(g.get('participants', []))} participantes"[:100])
                   for g in records[:25]]
        super().__init__(placeholder='Escolha um sorteio ativo', options=options)

    async def callback(self, interaction):
        mid = int(self.values[0])
        record = await self.cog.store.get_giveaway(interaction.guild_id, mid)
        if not record or record.get('status') != 'active':
            return await interaction.response.send_message('Este sorteio não está mais ativo.', ephemeral=True)
        await interaction.response.edit_message(content=None, embed=details(record), view=ManageActions(self.cog, mid))


def details(record):
    embed = discord.Embed(title='🎁 Gerenciar sorteio', description=str(record.get('prize', 'Prêmio'))[:2000], color=discord.Color.blurple())
    embed.add_field(name='Mensagem', value=f"[Abrir sorteio](https://discord.com/channels/{record.get('guild_id', '@me')}/{record['channel_id']}/{record['message_id']})", inline=False)
    embed.add_field(name='Participantes', value=str(len(record.get('participants', []))))
    embed.add_field(name='Vencedores previstos', value=str(record.get('winner_count', 1)))
    embed.add_field(name='Encerra em', value=str(record.get('ends_at', '—')), inline=False)
    return embed


class ManageList(discord.ui.View):
    def __init__(self, cog, records):
        super().__init__(timeout=600)
        self.cog = cog
        self.add_item(ManageSelect(cog, records))

    async def interaction_check(self, interaction):
        if not is_admin(interaction):
            await interaction.response.send_message('⛔ Requer Gerenciar Servidor.', ephemeral=True)
            return False
        return True


class ManageActions(discord.ui.View):
    def __init__(self, cog, message_id):
        super().__init__(timeout=600)
        self.cog = cog
        self.message_id = message_id

    async def interaction_check(self, interaction):
        if not is_admin(interaction):
            await interaction.response.send_message('⛔ Requer Gerenciar Servidor.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Atualizar detalhes', emoji='🔄', style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction, button):
        record = await self.cog.store.get_giveaway(interaction.guild_id, self.message_id)
        if not record:
            return await interaction.response.send_message('Sorteio não encontrado.', ephemeral=True)
        await interaction.response.edit_message(embed=details(record), view=self)

    @discord.ui.button(label='Encerrar agora', emoji='🔒', style=discord.ButtonStyle.danger)
    async def close(self, interaction, button):
        record = await self.cog.store.get_giveaway(interaction.guild_id, self.message_id)
        if not record or record.get('status') != 'active':
            return await interaction.response.send_message('Sorteio já encerrado.', ephemeral=True)
        await interaction.response.edit_message(content='Confirme o encerramento antecipado. Esta ação selecionará os vencedores.', embed=None,
                                                view=ConfirmClose(self.cog, self.message_id))

    @discord.ui.button(label='Voltar', emoji='↩️', style=discord.ButtonStyle.secondary)
    async def back(self, interaction, button):
        await show_manage(interaction, self.cog, edit=True)


class ConfirmClose(discord.ui.View):
    def __init__(self, cog, message_id):
        super().__init__(timeout=120)
        self.cog = cog
        self.message_id = message_id

    async def interaction_check(self, interaction):
        if not is_admin(interaction):
            await interaction.response.send_message('⛔ Requer Gerenciar Servidor.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Confirmar encerramento', style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        async with self.cog._closing:
            record = await self.cog.store.get_giveaway(interaction.guild_id, self.message_id)
            if record and record.get('status') == 'active':
                await self.cog.filter_eligible(interaction.guild_id, self.message_id, record)
            result = await self.cog.store.close_manually(interaction.guild_id, self.message_id, datetime.now(timezone.utc).isoformat())
        if result is None:
            return await interaction.edit_original_response(content='Sorteio já encerrado.', view=None)
        await interaction.edit_original_response(content='✅ Sorteio encerrado. O resultado será publicado automaticamente pelo verificador.', view=None)

    @discord.ui.button(label='Cancelar', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        record = await self.cog.store.get_giveaway(interaction.guild_id, self.message_id)
        await interaction.response.edit_message(content=None, embed=details(record), view=ManageActions(self.cog, self.message_id))


async def show_manage(interaction, cog, edit=False):
    guild = await cog.store.get_guild(interaction.guild_id)
    records = [dict(g, message_id=int(mid), guild_id=interaction.guild_id)
               for mid, g in guild.get('giveaways', {}).items() if g.get('status') == 'active']
    records.sort(key=lambda g: g.get('ends_at', ''))
    kwargs = dict(content=f'📋 **Sorteios ativos: {len(records)}**. Selecione um para gerenciar.' if records else '📋 Nenhum sorteio ativo.',
                  embed=None, view=ManageList(cog, records) if records else None)
    if edit:
        await interaction.response.edit_message(**kwargs)
    else:
        await interaction.response.send_message(**kwargs, ephemeral=True)
