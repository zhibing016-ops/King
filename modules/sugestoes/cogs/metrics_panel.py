import io
import csv
import discord
from discord import app_commands
from discord.ext import commands
from modules.sugestoes.storage import read_data
from modules.sugestoes.permissions import can_review
from modules.sugestoes.metrics import collect, format_summary

async def allowed(interaction):
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    data = await read_data(interaction.guild_id)
    return await can_review(interaction)

class MetricsView(discord.ui.View):
    def __init__(self, owner_id: int, guild_id: int, page: int = 0, mode: str = 'ranking'):
        super().__init__(timeout=300)
        self.owner_id, self.guild_id, self.page, self.mode = owner_id, guild_id, page, mode

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id or interaction.guild_id != self.guild_id:
            await interaction.response.send_message('Este painel pertence a outro administrador.', ephemeral=True)
            return False
        if not await allowed(interaction):
            await interaction.response.send_message('Acesso negado.', ephemeral=True)
            return False
        return True

    async def show(self, interaction):
        data = await read_data(self.guild_id)
        metrics = collect(data)
        if self.mode == 'resumo':
            embed = discord.Embed(title='📊 KING PLUS • Métricas', description=format_summary(metrics), color=discord.Color.blurple())
        else:
            items = metrics['ranking']; pages = max(1, (len(items) + 4) // 5)
            self.page = max(0, min(self.page, pages - 1))
            chunk = items[self.page*5:self.page*5+5]
            lines = [f"**#{r['id']}** • 👍 {r['up']} | 👎 {r['down']} | Saldo {r['saldo']:+d}\n{discord.utils.escape_markdown(r['titulo'])[:80]}" for r in chunk]
            embed = discord.Embed(title='🏆 KING PLUS • Classificação por votos', description='\n\n'.join(lines) if lines else 'Nenhuma sugestão.', color=discord.Color.blurple())
            embed.set_footer(text=f'Página {self.page+1}/{pages} • Ordenação por saldo de votos')
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='Resumo', style=discord.ButtonStyle.primary)
    async def resumo(self, interaction, button):
        self.mode='resumo'; await self.show(interaction)

    @discord.ui.button(label='Ranking', style=discord.ButtonStyle.secondary)
    async def ranking(self, interaction, button):
        self.mode='ranking'; self.page=0; await self.show(interaction)

    @discord.ui.button(label='◀', style=discord.ButtonStyle.secondary)
    async def prev(self, interaction, button):
        self.mode='ranking'; self.page=max(0,self.page-1); await self.show(interaction)

    @discord.ui.button(label='▶', style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        self.mode='ranking'; self.page+=1; await self.show(interaction)

    @discord.ui.button(label='Atualizar', style=discord.ButtonStyle.success)
    async def refresh(self, interaction, button):
        await self.show(interaction)

class MetricsCog(commands.Cog):
    def __init__(self, bot): self.bot=bot

    @app_commands.command(name='sugestao_metricas', description='Abre o painel de estatísticas e ranking')
    @app_commands.guild_only()
    async def metricas(self, interaction: discord.Interaction):
        if not await allowed(interaction):
            return await interaction.response.send_message('Acesso restrito à equipe de sugestões.', ephemeral=True)
        metrics = collect(await read_data(interaction.guild_id))
        embed = discord.Embed(title='📊 KING PLUS • Métricas', description=format_summary(metrics), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=MetricsView(interaction.user.id, interaction.guild_id, mode='resumo'), ephemeral=True)

    @app_commands.command(name='sugestao_relatorio', description='Exporta relatório CSV com métricas das sugestões')
    @app_commands.guild_only()
    async def relatorio(self, interaction: discord.Interaction):
        if not await allowed(interaction):
            return await interaction.response.send_message('Acesso restrito à equipe de sugestões.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        metrics = collect(await read_data(interaction.guild_id))
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['id', 'titulo', 'status', 'positivos', 'negativos', 'saldo'])
        for r in metrics['ranking']:
            writer.writerow([r['id'], r['titulo'], r['status'], r['up'], r['down'], r['saldo']])
        raw = output.getvalue().encode('utf-8-sig')
        file = discord.File(io.BytesIO(raw), filename=f'sugestoes_{interaction.guild_id}.csv')
        await interaction.followup.send(content='Relatório de sugestões (sem identificação dos autores).', file=file, ephemeral=True)

async def setup(bot):
    await bot.add_cog(MetricsCog(bot))
