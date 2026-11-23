import discord
from discord import app_commands
from discord.ext import commands
from modules.enquetes.storage import read
from modules.enquetes.manager import create, update, counts
from modules.enquetes.embeds import render
from modules.enquetes.views import PollView

def admin(interaction):
    return interaction.guild is not None and interaction.user.guild_permissions.manage_guild

class CreateModal(discord.ui.Modal, title="Criar enquete KING PLUS"):
    question=discord.ui.TextInput(label="Pergunta",max_length=250)
    options=discord.ui.TextInput(label="Opções (uma por linha)",style=discord.TextStyle.paragraph,max_length=1500)
    duration=discord.ui.TextInput(label="Duração em minutos",default="60",max_length=6)
    async def on_submit(self,interaction):
        try:
            minutes=int(str(self.duration)); assert 1<=minutes<=10080
            p=await create(interaction.guild_id,interaction.user.id,str(self.question),str(self.options).splitlines(),minutes)
        except (ValueError,AssertionError) as e:
            return await interaction.response.send_message(f"Dados inválidos: {e}",ephemeral=True)
        await interaction.response.send_message(f"Rascunho `{p['id']}` criado. Use **Enquetes** para publicar.",ephemeral=True)

class PollPicker(discord.ui.Select):
    def __init__(self,action,polls):
        self.action=action
        super().__init__(placeholder="Escolha a enquete",options=[discord.SelectOption(label=p['question'][:90],description=f"{p['status']} • {p['id']}",value=p['id']) for p in polls[:25]])
    async def callback(self,interaction):
        if not admin(interaction):return await interaction.response.send_message("Acesso negado.",ephemeral=True)
        p=read('polls',{}).get(self.values[0]);
        if not p or p['guild_id']!=interaction.guild_id:return await interaction.response.send_message("Enquete indisponível.",ephemeral=True)
        if self.action=='publish':
            if p['status']!='draft':return await interaction.response.send_message("Somente rascunhos podem ser publicados.",ephemeral=True)
            await interaction.response.defer(ephemeral=True)
            msg=await interaction.channel.send(embed=render({**p,'status':'open'}),view=PollView(p))
            p.update(status='open',message_id=msg.id,channel_id=msg.channel.id)
            await update(p)
            await interaction.followup.send("Enquete publicada neste canal.",ephemeral=True)
        elif self.action=='close':
            p['status']='closed';await update(p)
            if p.get('channel_id') and p.get('message_id'):
                try:
                    channel=interaction.client.get_channel(p['channel_id']) or await interaction.client.fetch_channel(p['channel_id'])
                    msg=await channel.fetch_message(p['message_id']);await msg.edit(embed=render(p),view=None)
                except (discord.HTTPException,discord.Forbidden):pass
            await interaction.response.send_message("Enquete encerrada.",ephemeral=True)
        else:
            n=sum(counts(p));await interaction.response.send_message(f"**{p['question']}**\nEstado: {p['status']}\nVotos registrados: {len(p['votes'])}\nSeleções: {n}",ephemeral=True)

class PickerView(discord.ui.View):
    def __init__(self,action,polls):
        super().__init__(timeout=180);self.add_item(PollPicker(action,polls))

class MainPanel(discord.ui.View):
    def __init__(self):super().__init__(timeout=300)
    async def pick(self,interaction,action):
        polls=[p for p in read('polls',{}).values() if p.get('guild_id')==interaction.guild_id and (action!='publish' or p['status']=='draft') and (action!='close' or p['status']=='open')]
        if not polls:return await interaction.response.send_message("Nenhuma enquete disponível para essa ação.",ephemeral=True)
        await interaction.response.send_message("Selecione uma enquete:",view=PickerView(action,polls[-25:]),ephemeral=True)
    @discord.ui.button(label="Criar Enquete",style=discord.ButtonStyle.primary,row=0)
    async def criar(self,i,b):await i.response.send_modal(CreateModal())
    @discord.ui.button(label="Enquetes",style=discord.ButtonStyle.secondary,row=0)
    async def enquetes(self,i,b):await self.pick(i,'publish')
    @discord.ui.button(label="Votações",style=discord.ButtonStyle.secondary,row=0)
    async def votacoes(self,i,b):await self.pick(i,'close')
    @discord.ui.button(label="Agendamentos",style=discord.ButtonStyle.secondary,row=1)
    async def agendamentos(self,i,b):
        polls=[p for p in read('polls',{}).values() if p.get('guild_id')==i.guild_id and p['status']=='draft']
        await i.response.send_message("Rascunhos aguardando publicação: "+str(len(polls))+". O agendamento avançado permanece no módulo legado.",ephemeral=True)
    @discord.ui.button(label="Resultados",style=discord.ButtonStyle.secondary,row=1)
    async def resultados(self,i,b):await self.pick(i,'results')
    @discord.ui.button(label="Configurações",style=discord.ButtonStyle.secondary,row=1)
    async def config(self,i,b):await i.response.send_message("Configuração atual: dados em JSON; administração restrita a Gerenciar Servidor; votos por seleção. Configurações avançadas exigem integração adicional.",ephemeral=True)
    @discord.ui.button(label="Estatísticas",style=discord.ButtonStyle.secondary,row=2)
    async def stats(self,i,b):
        polls=[p for p in read('polls',{}).values() if p.get('guild_id')==i.guild_id]
        await i.response.send_message(f"Enquetes: {len(polls)} | Abertas: {sum(p['status']=='open' for p in polls)} | Encerradas: {sum(p['status']=='closed' for p in polls)} | Participantes: {sum(len(p['votes']) for p in polls)}",ephemeral=True)
    @discord.ui.button(label="Manutenção",style=discord.ButtonStyle.secondary,row=2)
    async def maintenance(self,i,b):await i.response.send_message("Armazenamento JSON ativo. Faça cópia da pasta data antes de restaurar arquivos.",ephemeral=True)
    @discord.ui.button(label="Voltar",style=discord.ButtonStyle.secondary,row=3)
    async def back(self,i,b):await i.response.edit_message(content="Painel de Enquetes fechado.",embed=None,view=None)
    @discord.ui.button(label="Central",style=discord.ButtonStyle.secondary,row=3)
    async def central(self,i,b):await i.response.send_message("Abra `/kingplus` para acessar a Central KING PLUS, se instalada.",ephemeral=True)

class Enquetes(commands.Cog):
    def __init__(self,bot):self.bot=bot
    @app_commands.command(name='enquetes',description='Abrir o painel principal de Enquetes KING PLUS')
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def painel(self,interaction:discord.Interaction):
        if not admin(interaction):return await interaction.response.send_message('Você precisa da permissão Gerenciar Servidor.',ephemeral=True)
        embed=discord.Embed(title='👑 KING PLUS — Enquetes',description='Gerenciamento completo de votações',color=discord.Color.blurple())
        embed.set_footer(text='Armazenamento: JSON • Admin')
        await interaction.response.send_message(embed=embed,view=MainPanel(),ephemeral=True)

async def setup(bot):
    await bot.add_cog(Enquetes(bot))
    for p in read('polls',{}).values():
        if p.get('status')=='open' and p.get('message_id'):
            bot.add_view(PollView(p),message_id=p['message_id'])
