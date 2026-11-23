"""Relatórios privados via painel administrativo do Discord."""
import discord
from .permissions import admin_only
from ..services.statistics import EVENT_LABELS, report_from_guild

PERIODS = ((7, '7 dias'), (30, '30 dias'), (None, 'Todo o histórico retido'))

def _safe(text):
    return discord.utils.escape_mentions(discord.utils.escape_markdown(str(text)))

def build_report_embed(stats, guild):
    period = next(label for days, label in PERIODS if days == stats['period_days'])
    embed = discord.Embed(title='📊 KING PLUS • Estatísticas de cargos',
                          description=f'Período: **{period}**\nDados extraídos da auditoria JSON.',
                          color=discord.Color.blurple())
    counts = stats['counts']
    embed.add_field(name='Eventos registrados', value=str(stats['events']))
    embed.add_field(name='Usuários distintos', value=str(stats['unique_users']))
    embed.add_field(name='Cargos atribuídos', value=str(counts.get('grant', 0)))
    embed.add_field(name='Remoções', value=str(counts.get('revoke', 0)))
    embed.add_field(name='Expirações', value=str(counts.get('expire', 0)))
    embed.add_field(name='Bloqueios / Erros', value=f"{counts.get('denied', 0)} / {counts.get('error', 0)}")
    top = []
    for role_id, count in stats['top_roles'][:5]:
        role = guild.get_role(int(role_id)) if guild else None
        label = _safe(role.name) if role else f'ID {role_id}'
        top.append(f'**{label}** — {count} concessão(ões)')
    embed.add_field(name='🏆 Cargos mais atribuídos', value='\n'.join(top) or 'Sem atribuições registradas', inline=False)
    sources = [f'{_safe(name)[:80]}: {count}' for name,count in stats['sources'][:5]]
    embed.add_field(name='Origem dos eventos', value='\n'.join(sources) or 'Sem dados', inline=False)
    embed.set_footer(text=f"Histórico limitado aos {stats['history_limit']} últimos eventos por servidor • {stats['retained_records']} retidos")
    return embed

class StatisticsView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id

    async def interaction_check(self, interaction):
        return await admin_only(interaction, self.guild_id, self.owner_id)

    async def respond(self, interaction, days):
        stats = report_from_guild(await self.store.get(self.guild_id), days=days)
        await interaction.response.send_message(embed=build_report_embed(stats, interaction.guild), ephemeral=True)

    @discord.ui.button(label='Últimos 7 dias', emoji='📅', style=discord.ButtonStyle.primary)
    async def seven(self, interaction, button):
        await self.respond(interaction, 7)

    @discord.ui.button(label='Últimos 30 dias', emoji='🗓️', style=discord.ButtonStyle.secondary)
    async def thirty(self, interaction, button):
        await self.respond(interaction, 30)

    @discord.ui.button(label='Histórico completo', emoji='📊', style=discord.ButtonStyle.secondary)
    async def all_history(self, interaction, button):
        await self.respond(interaction, None)

    @discord.ui.button(label='Atividade diária', emoji='📈', style=discord.ButtonStyle.secondary, row=1)
    async def daily(self, interaction, button):
        stats = report_from_guild(await self.store.get(self.guild_id), days=30)
        lines = [f'`{day}`: **{count}** evento(s)' for day, count in stats['daily'][-25:]]
        await interaction.response.send_message('**KING PLUS • Atividade diária (30 dias)**\n' +
                                                ('\n'.join(lines) or 'Sem eventos registrados.'), ephemeral=True)
