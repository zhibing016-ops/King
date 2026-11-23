import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import discord
from .create_panel import parse_duration

TZ = ZoneInfo('America/Sao_Paulo')

class ScheduleModal(discord.ui.Modal, title='📅 Agendar sorteio KING PLUS'):
    prize = discord.ui.TextInput(label='Prêmio', max_length=150)
    description = discord.ui.TextInput(label='Descrição', required=False, style=discord.TextStyle.paragraph, max_length=900)
    start = discord.ui.TextInput(label='Início (DD/MM/AAAA HH:MM, Brasília)', placeholder='25/12/2026 18:30', max_length=16)
    duration = discord.ui.TextInput(label='Duração (30m, 2h, 7d)', max_length=12)
    winners = discord.ui.TextInput(label='Vencedores (1 a 20)', default='1', max_length=2)

    def __init__(self, cog, channel, recurrence=None):
        super().__init__()
        self.cog, self.channel, self.recurrence = cog, channel, recurrence

    async def on_submit(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message('⛔ Gerenciar Servidor necessário.', ephemeral=True)
        try:
            start = datetime.strptime(str(self.start).strip(), '%d/%m/%Y %H:%M').replace(tzinfo=TZ).astimezone(timezone.utc)
            now = datetime.now(timezone.utc)
            if not now + timedelta(minutes=1) <= start <= now + timedelta(days=365):
                raise ValueError('Agende entre 1 minuto e 365 dias a partir de agora.')
            duration = parse_duration(str(self.duration))
            winners = int(str(self.winners))
            if not 1 <= winners <= 20:
                raise ValueError('Informe entre 1 e 20 vencedores.')
        except (ValueError, OverflowError) as error:
            return await interaction.response.send_message(f'❌ Dados inválidos: {error}', ephemeral=True)
        config = await self.cog.store.get_guild(interaction.guild_id)
        if not config.get('enabled', True):
            return await interaction.response.send_message('🛠️ Sistema desativado.', ephemeral=True)
        me = interaction.guild.me
        perms = self.channel.permissions_for(me)
        if not (perms.send_messages and perms.embed_links and perms.view_channel):
            return await interaction.response.send_message('❌ Preciso de acesso, Enviar Mensagens e Inserir Links no canal.', ephemeral=True)
        record = {'id': uuid.uuid4().hex[:12], 'guild_id': interaction.guild_id,
                  'channel_id': self.channel.id, 'host_id': interaction.user.id,
                  'prize': str(self.prize), 'description': str(self.description),
                  'starts_at': start.isoformat(), 'duration_seconds': duration,
                  'winner_count': winners, 'requirements': dict(config.get('requirements', {'role_id': None, 'min_days': 0})),
                  'appearance': dict(config.get('appearance', {})), 'status': 'pending'}
        if self.recurrence:
            record['recurrence'] = self.recurrence
            record['anchor_day'] = start.astimezone(TZ).day
            record['occurrences'] = 0
        await self.cog.store.add_schedule(interaction.guild_id, record)
        await interaction.response.send_message(f'✅ Sorteio agendado! ID `{record["id"]}`\nCanal: {self.channel.mention}\nInício: <t:{int(start.timestamp())}:F>', ephemeral=True)

class ScheduleChannelPicker(discord.ui.View):
    def __init__(self, cog, recurrence=None):
        super().__init__(timeout=180)
        self.cog, self.recurrence = cog, recurrence

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder='Canal para publicação automática')
    async def choose(self, interaction, select):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message('⛔ Gerenciar Servidor necessário.', ephemeral=True)
        channel = interaction.guild.get_channel(select.values[0].id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message('❌ Selecione um canal de texto.', ephemeral=True)
        await interaction.response.send_modal(ScheduleModal(self.cog, channel, self.recurrence))

class SchedulePanel(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def interaction_check(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message('⛔ Gerenciar Servidor necessário.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Agendar novo', emoji='📅', style=discord.ButtonStyle.success)
    async def create(self, interaction, button):
        await interaction.response.send_message('Escolha o canal:', view=ScheduleChannelPicker(self.cog), ephemeral=True)

    @discord.ui.select(placeholder='Criar sorteio recorrente', options=[
        discord.SelectOption(label='Diário', value='daily'),
        discord.SelectOption(label='Semanal', value='weekly'),
        discord.SelectOption(label='Mensal', value='monthly')])
    async def recurrence_picker(self, interaction, select):
        await interaction.response.send_message(
            'Escolha o canal para o sorteio recorrente:',
            view=ScheduleChannelPicker(self.cog, select.values[0]), ephemeral=True)

    @discord.ui.button(label='Listar recorrentes', emoji='🔁', style=discord.ButtonStyle.secondary)
    async def recurring_list(self, interaction, button):
        records = await self.cog.store.recurring_for_guild(interaction.guild_id)
        if not records:
            return await interaction.response.send_message('Nenhum sorteio recorrente ativo.', ephemeral=True)
        lines = [f'`{r["id"]}` • {discord.utils.escape_markdown(r["prize"][:55])} • {r["recurrence"]} • próxima: <t:{int(datetime.fromisoformat(r["starts_at"]).timestamp())}:F>' for r in records[:15]]
        await interaction.response.send_message('🔁 **Sorteios recorrentes**\n' + '\n'.join(lines), ephemeral=True)

    @discord.ui.button(label='Listar agendados', emoji='📋', style=discord.ButtonStyle.primary)
    async def listing(self, interaction, button):
        records = await self.cog.store.scheduled_for_guild(interaction.guild_id)
        if not records:
            return await interaction.response.send_message('Nenhum sorteio pendente.', ephemeral=True)
        lines = [f'`{r["id"]}` • {discord.utils.escape_markdown(r["prize"][:70])} • <t:{int(datetime.fromisoformat(r["starts_at"]).timestamp())}:F>' for r in records[:20]]
        await interaction.response.send_message('📅 **Sorteios agendados**\n' + '\n'.join(lines), ephemeral=True)

async def show_schedule(interaction, cog):
    await interaction.response.send_message('📅 **Agendamento de sorteios**\nHorários no fuso de Brasília.', view=SchedulePanel(cog), ephemeral=True)
