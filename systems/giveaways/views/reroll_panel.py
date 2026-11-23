import discord
from datetime import datetime, timezone
from .admin_panel import is_admin


class RerollSelect(discord.ui.Select):
    def __init__(self, cog, records):
        self.cog = cog
        options = [discord.SelectOption(label=str(r.get('prize', 'Prêmio'))[:90], value=str(r['message_id']), description=f"{len(r.get('participants', []))} participantes") for r in records[:25]]
        super().__init__(placeholder='Selecione um sorteio encerrado', options=options)

    async def callback(self, interaction):
        mid = int(self.values[0])
        record = await self.cog.store.get_giveaway(interaction.guild_id, mid)
        if not record or record.get('status') != 'ended':
            return await interaction.response.send_message('Sorteio indisponível.', ephemeral=True)
        await interaction.response.send_modal(RerollModal(self.cog, mid))


class RerollList(discord.ui.View):
    def __init__(self, cog, records):
        super().__init__(timeout=600)
        self.add_item(RerollSelect(cog, records))

    async def interaction_check(self, interaction):
        if not is_admin(interaction):
            await interaction.response.send_message('⛔ Requer Gerenciar Servidor.', ephemeral=True)
            return False
        return True


class RerollModal(discord.ui.Modal, title='🏆 Sortear novos vencedores'):
    quantidade = discord.ui.TextInput(label='Quantidade de novos vencedores (1–20)', default='1', max_length=2)

    def __init__(self, cog, message_id):
        super().__init__()
        self.cog = cog
        self.message_id = message_id

    async def on_submit(self, interaction):
        if not is_admin(interaction):
            return await interaction.response.send_message('⛔ Permissão insuficiente.', ephemeral=True)
        try:
            amount = int(self.quantidade.value)
        except ValueError:
            return await interaction.response.send_message('Informe um número inteiro.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with self.cog._closing:
            record = await self.cog.store.get_giveaway(interaction.guild_id, self.message_id)
            if not record:
                return await interaction.followup.send('Sorteio não encontrado.', ephemeral=True)
            eligible = await self.cog.eligible_ended(interaction.guild_id, record)
            try:
                result = await self.cog.store.reroll(interaction.guild_id, self.message_id, amount, datetime.now(timezone.utc).isoformat(), eligible)
            except ValueError as error:
                return await interaction.followup.send(f'⚠️ {error}', ephemeral=True)
        winners = ', '.join(f'<@{uid}>' for uid in result['winners'])
        await interaction.followup.send(f'🏆 Novos vencedores: {winners}. A mensagem original será atualizada em até 30 segundos.', ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def show_reroll(interaction, cog):
    guild = await cog.store.get_guild(interaction.guild_id)
    records = [dict(r, message_id=int(mid)) for mid, r in guild.get('giveaways', {}).items() if r.get('status') == 'ended']
    records.sort(key=lambda r: r.get('ended_at', ''), reverse=True)
    await interaction.response.send_message('🏆 Selecione um sorteio encerrado para substituir vencedores.' if records else 'Nenhum sorteio encerrado.', view=RerollList(cog, records) if records else None, ephemeral=True)
