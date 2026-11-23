import datetime
import re
import discord
from .appearance_panel import appearance_of, build_embed
from .participation import ParticipationView

DURATION_RE = re.compile(r'^(\d+)([mhd])$', re.I)

def parse_duration(value):
    match = DURATION_RE.fullmatch(value.strip())
    if not match:
        raise ValueError('Use duração como 30m, 2h ou 7d.')
    count = int(match.group(1))
    seconds = count * {'m': 60, 'h': 3600, 'd': 86400}[match.group(2).lower()]
    if seconds < 60 or seconds > 30 * 86400:
        raise ValueError('A duração deve ficar entre 1 minuto e 30 dias.')
    return seconds

class CreateGiveawayModal(discord.ui.Modal, title='🎁 Criar sorteio KING PLUS'):
    prize = discord.ui.TextInput(label='Prêmio', placeholder='Ex.: Nitro Discord', max_length=150)
    description = discord.ui.TextInput(label='Descrição', style=discord.TextStyle.paragraph, required=False, max_length=900)
    duration = discord.ui.TextInput(label='Duração (m/h/d)', placeholder='Ex.: 30m, 2h, 7d', max_length=12)
    winners = discord.ui.TextInput(label='Quantidade de vencedores (1 a 20)', placeholder='1', default='1', max_length=2)

    def __init__(self, cog, channel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message('⛔ Permissão Gerenciar Servidor necessária.', ephemeral=True)
        try:
            seconds = parse_duration(str(self.duration))
            winners = int(str(self.winners))
            if not 1 <= winners <= 20:
                raise ValueError('A quantidade de vencedores deve ser entre 1 e 20.')
        except ValueError as error:
            return await interaction.response.send_message(f'❌ {error}', ephemeral=True)
        if not self.channel.permissions_for(interaction.guild.me).send_messages or not self.channel.permissions_for(interaction.guild.me).embed_links:
            return await interaction.response.send_message('❌ Preciso de Enviar Mensagens e Inserir Links no canal escolhido.', ephemeral=True)
        config = await self.cog.store.get_guild(interaction.guild_id)
        if not config.get('enabled', True):
            return await interaction.response.send_message('🛠️ Sorteios desativados para manutenção.', ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        end = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
        embed = build_embed(str(self.prize), str(self.description), winners, end, appearance_of(config))
        try:
            embed.add_field(name="Participantes", value="0", inline=True)
            message = await self.channel.send(embed=embed, view=ParticipationView(self.cog))
        except discord.HTTPException:
            return await interaction.followup.send('❌ Não foi possível publicar no canal.', ephemeral=True)
        record = {
            'message_id': message.id, 'guild_id': interaction.guild_id, 'channel_id': self.channel.id,
            'host_id': interaction.user.id, 'prize': str(self.prize), 'description': str(self.description),
            'winner_count': winners, 'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'ends_at': end.isoformat(), 'status': 'active', 'participants': [], 'winners': [],
            'requirements': dict(config.get('requirements', {'role_id': None, 'min_days': 0}))
        }
        try:
            await self.cog.store.add_giveaway(interaction.guild_id, record)
        except Exception:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            return await interaction.followup.send('❌ Falha ao salvar sorteio no JSON. Publicação revertida.', ephemeral=True)
        await interaction.followup.send(f'✅ Sorteio publicado em {self.channel.mention}: {message.jump_url}\n🎉 Os membros já podem participar pelo botão. O sorteio será encerrado automaticamente no prazo.', ephemeral=True)

class ChannelPicker(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=180)
        self.cog = cog

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder='Selecione o canal do sorteio', min_values=1, max_values=1)
    async def choose(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message('⛔ Gerenciar Servidor necessário.', ephemeral=True)
        channel = interaction.guild.get_channel(select.values[0].id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message('❌ Selecione um canal de texto válido.', ephemeral=True)
        await interaction.response.send_modal(CreateGiveawayModal(self.cog, channel))
