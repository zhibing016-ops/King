import csv
import io
import discord
from discord import app_commands
from discord.ext import commands
from modules.sugestoes.storage import read_data
from modules.sugestoes.permissions import can_review
from modules.sugestoes.activity_reports import build_report, PERIODS

LABELS = {'7d':'7 dias','30d':'30 dias','90d':'90 dias','total':'Todo o histórico registrado'}

def report_embed(report, page=0, mode='resumo'):
    embed=discord.Embed(title='📈 KING PLUS • Acompanhamento',color=discord.Color.blurple())
    if mode=='ranking':
        rows=report['ranking']; pages=max(1,(len(rows)+4)//5); page=max(0,min(page,pages-1))
        chunk=rows[page*5:page*5+5]
        embed.description='\n\n'.join(f"**#{x['id']}** • 👍 {x['up']} | 👎 {x['down']} | Saldo {x['saldo']:+d}\n{discord.utils.escape_markdown(x['titulo'])}" for x in chunk) or 'Nenhuma sugestão com criação registrada neste período.'
        embed.set_footer(text=f"{LABELS[report['period']]} • Página {page+1}/{pages} • Votos atuais, não históricos")
    else:
        top=sorted(report['counts'].items(),key=lambda x:(-x[1],x[0]))[:8]
        embed.description=(f"**Período:** {LABELS[report['period']]}\n"
                           f"**Eventos registrados:** {report['events']}\n"
                           f"**Sugestões criadas (registradas):** {report['created']}\n"
                           f"**Mudanças de status:** {report['status_changes']}\n\n"
                           '**Atividades:**\n'+('\n'.join(f'• {discord.utils.escape_markdown(k[:45])}: {v}' for k,v in top) or 'Sem eventos registrados.'))
        embed.set_footer(text='Dados limitados à auditoria retida (até 5.000 eventos).')
    return embed

class ActivityView(discord.ui.View):
    def __init__(self,user_id,guild_id,period='30d'):
        super().__init__(timeout=300)
        self.user_id=user_id;self.guild_id=guild_id;self.period=period;self.mode='resumo';self.page=0

    async def interaction_check(self,interaction):
        if interaction.guild_id!=self.guild_id or interaction.user.id!=self.user_id or not await can_review(interaction):
            await interaction.response.send_message('Acesso negado.',ephemeral=True)
            return False
        return True

    async def render(self,interaction):
        report=build_report(await read_data(self.guild_id),self.period)
        self.page=max(0,min(self.page,max(0,(len(report['ranking'])-1)//5)))
        await interaction.response.edit_message(embed=report_embed(report,self.page,self.mode),view=self)

    @discord.ui.select(placeholder='Selecionar período',options=[discord.SelectOption(label=LABELS[p],value=p) for p in PERIODS])
    async def period_select(self,interaction,select):
        self.period=select.values[0];self.page=0;await self.render(interaction)

    @discord.ui.button(label='Resumo',style=discord.ButtonStyle.primary,row=1)
    async def summary(self,interaction,button):
        self.mode='resumo';await self.render(interaction)

    @discord.ui.button(label='Ranking',style=discord.ButtonStyle.secondary,row=1)
    async def ranking(self,interaction,button):
        self.mode='ranking';self.page=0;await self.render(interaction)

    @discord.ui.button(label='Anterior',style=discord.ButtonStyle.secondary,row=1)
    async def previous(self,interaction,button):
        self.mode='ranking';self.page=max(0,self.page-1);await self.render(interaction)

    @discord.ui.button(label='Próxima',style=discord.ButtonStyle.secondary,row=1)
    async def following(self,interaction,button):
        self.mode='ranking';self.page+=1;await self.render(interaction)

    @discord.ui.button(label='Atualizar',style=discord.ButtonStyle.success,row=2)
    async def refresh(self,interaction,button):
        await self.render(interaction)

class ActivityCog(commands.Cog):
    def __init__(self,bot): self.bot=bot

    @app_commands.command(name='sugestao_atividades',description='Painel de relatórios e ranking por período')
    @app_commands.guild_only()
    async def atividades(self,interaction:discord.Interaction):
        if not await can_review(interaction):
            return await interaction.response.send_message('Acesso restrito à equipe.',ephemeral=True)
        view=ActivityView(interaction.user.id,interaction.guild_id)
        report=build_report(await read_data(interaction.guild_id),'30d')
        await interaction.response.send_message(embed=report_embed(report),view=view,ephemeral=True)

    @app_commands.command(name='sugestao_atividades_csv',description='Exporta atividades registradas em CSV')
    @app_commands.describe(periodo='Período dos registros')
    @app_commands.choices(periodo=[app_commands.Choice(name=LABELS[p],value=p) for p in PERIODS])
    @app_commands.guild_only()
    async def atividades_csv(self,interaction:discord.Interaction,periodo:str='30d'):
        if not await can_review(interaction):
            return await interaction.response.send_message('Acesso restrito à equipe.',ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        report=build_report(await read_data(interaction.guild_id),periodo)
        output=io.StringIO(newline='');writer=csv.writer(output)
        writer.writerow(['data_utc','quantidade_eventos'])
        for day,n in report['daily'].items():writer.writerow([day,n])
        file=discord.File(io.BytesIO(output.getvalue().encode('utf-8-sig')),filename=f'kingplus_atividades_{periodo}.csv')
        await interaction.followup.send(content='Atividades por dia (somente eventos registrados na auditoria).',file=file,ephemeral=True)

async def setup(bot):
    await bot.add_cog(ActivityCog(bot))
