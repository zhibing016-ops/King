import discord
from ..statistics import summarize


def stats_embed(data):
    e = discord.Embed(title='📊 KING PLUS • Estatísticas de sorteios', color=discord.Color.blurple())
    e.add_field(name='🎁 Criados', value=str(data['total']))
    e.add_field(name='🟢 Ativos', value=str(data['active']))
    e.add_field(name='🔒 Encerrados', value=str(data['ended']))
    e.add_field(name='🎟️ Participações registradas', value=str(data['entries']))
    e.add_field(name='👥 Participantes únicos', value=str(data['unique_participants']))
    e.add_field(name='🏆 Vencedores registrados', value=str(data['winners']))
    e.add_field(name='👑 Vencedores únicos', value=str(data['unique_winners']))
    e.add_field(name='🔄 Rerolls', value=str(data['rerolls']))
    e.set_footer(text='Dados atuais do JSON • contagens históricas dependem dos registros preservados')
    return e


def ranking_embed(data):
    e = discord.Embed(title='📈 KING PLUS • Sorteios mais populares', color=discord.Color.blurple())
    lines = []
    for i, record in enumerate(data['top'], 1):
        prize = discord.utils.escape_markdown(str(record.get('prize', 'Sem prêmio')))[:80]
        count = len(set(map(str, record.get('participants', []))))
        lines.append(f'{i}. **{prize}** — {count} participante(s)')
    e.description = '\n'.join(lines) if lines else 'Nenhum sorteio registrado.'
    e.set_footer(text='Ranking por participantes atualmente armazenados')
    return e


class StatsPanel(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=600)
        self.cog = cog

    async def interaction_check(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message('⛔ Requer Gerenciar Servidor.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Resumo', emoji='📊', style=discord.ButtonStyle.primary)
    async def overview(self, interaction, button):
        data = summarize(await self.cog.store.get_guild(interaction.guild_id))
        await interaction.response.edit_message(embed=stats_embed(data), view=StatsPanel(self.cog))

    @discord.ui.button(label='Mais populares', emoji='📈', style=discord.ButtonStyle.secondary)
    async def popular(self, interaction, button):
        data = summarize(await self.cog.store.get_guild(interaction.guild_id))
        await interaction.response.edit_message(embed=ranking_embed(data), view=StatsPanel(self.cog))

    @discord.ui.button(label='Ranking de vencedores', emoji='🏆', style=discord.ButtonStyle.secondary)
    async def winners(self, interaction, button):
        data = summarize(await self.cog.store.get_guild(interaction.guild_id))
        lines = [f'{i}. <@{uid}> — {count} vitória(s)' for i, (uid, count) in enumerate(data['winner_ranking'], 1)]
        e = discord.Embed(title='🏆 KING PLUS • Ranking de vencedores', description='\n'.join(lines) if lines else 'Nenhum vencedor registrado.', color=discord.Color.gold())
        await interaction.response.edit_message(embed=e, view=StatsPanel(self.cog))


async def show_statistics(interaction, cog):
    data = summarize(await cog.store.get_guild(interaction.guild_id))
    await interaction.response.send_message(embed=stats_embed(data), view=StatsPanel(cog), ephemeral=True)
