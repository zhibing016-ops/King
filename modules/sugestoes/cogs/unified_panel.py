"""Painel único de sugestões: um único slash command /sugestao."""
import discord
from discord import app_commands
from discord.ext import commands
from modules.sugestoes.storage import read_data, mutate


def authorized(i):
    return bool(i.guild and i.user.guild_permissions.manage_guild)


async def call(i, cog, command, *args):
    target = i.client.get_cog(cog)
    if target is None:
        return await i.response.send_message("Módulo indisponível.", ephemeral=True)
    cmd = getattr(target, command, None)
    if cmd is None:
        return await i.response.send_message("Recurso indisponível.", ephemeral=True)
    try:
        await cmd.callback(target, i, *args)
    except Exception:
        if not i.response.is_done():
            await i.response.send_message("Não foi possível concluir a operação. Confira as permissões e os logs do bot.", ephemeral=True)
        raise


class NumberModal(discord.ui.Modal, title="Gerenciar sugestão"):
    numero = discord.ui.TextInput(label="Número da sugestão", placeholder="Ex.: 15", max_length=12)
    def __init__(self, status):
        super().__init__();self.status=status
    async def on_submit(self, i):
        if not self.numero.value.isdecimal():
            return await i.response.send_message("Informe um número válido.", ephemeral=True)
        await call(i, "Suggestions", "sugestao_status", int(self.numero.value), self.status)


class ChannelModal(discord.ui.Modal, title="Configurar canal"):
    canal = discord.ui.TextInput(label="ID do canal de texto", placeholder="Ative o modo desenvolvedor e copie o ID", max_length=22)
    def __init__(self, cog, command):
        super().__init__();self.cog=cog;self.command=command
    async def on_submit(self, i):
        if not self.canal.value.isdecimal() or not i.guild:
            return await i.response.send_message("ID inválido.", ephemeral=True)
        channel=i.guild.get_channel(int(self.canal.value))
        if not isinstance(channel,discord.TextChannel):
            return await i.response.send_message("Canal de texto não encontrado.", ephemeral=True)
        await call(i,self.cog,self.command,channel)


class ActionButton(discord.ui.Button):
    def __init__(self, label, action, row=0, style=discord.ButtonStyle.secondary):
        super().__init__(label=label, style=style, row=row)
        self.action=action
    async def callback(self, i):
        if not authorized(i):
            return await i.response.send_message("Somente administradores com Gerenciar Servidor.", ephemeral=True)
        action=self.action
        if action=="home":
            return await i.response.edit_message(embed=home_embed(),view=Home())
        if action=="back":
            return await i.response.edit_message(embed=home_embed(),view=Home())
        if action in SECTIONS:
            return await i.response.edit_message(embed=discord.Embed(title="KING PLUS • "+SECTIONS[action][0],description="Selecione uma opção.",color=discord.Color.blurple()),view=Section(action))
        if action.startswith("status:"):
            return await i.response.send_modal(NumberModal(action.split(":",1)[1]))
        if action in CHANNEL_ACTIONS:
            return await i.response.send_modal(ChannelModal(*CHANNEL_ACTIONS[action]))
        if action in CALLS:
            await call(i,*CALLS[action]);return
        await i.response.send_message("Recurso não disponível neste painel.",ephemeral=True)


SECTIONS={
 "painel":("Criar Painel",[("Configurar canal","channel"),("Publicar painel","publish"),("Personalizar","appearance")]),
 "sugestoes":("Sugestões",[("Fila de análise","queue"),("Aprovar","status:Aprovada"),("Rejeitar","status:Rejeitada"),("Em análise","status:Em análise"),("Reabrir","status:Pendente"),("Painel de análise","admin_panel")]),
 "equipe":("Equipe",[("Gerenciar cargos","team")]),
 "votos":("Votações",[("Ranking e métricas","metrics"),("Relatório CSV","report")]),
 "logs":("Logs",[("Configurar canal","log_channel"),("Histórico","history")]),
 "config":("Configurações",[("Anti-spam","antispam"),("Notificações DM","dm_config"),("Discussões","discussion_config"),("Anonimato: ativar","anon_on"),("Anonimato: desativar","anon_off")]),
 "stats":("Estatísticas",[("Painel de métricas","metrics"),("Atividades","activities"),("Exportar CSV","report")]),
 "maintenance":("Manutenção",[("Abrir painel","maintenance_panel")]),
}
CHANNEL_ACTIONS={"channel":("Suggestions","sugestao_canal"),"publish":("Suggestions","sugestao_painel"),"admin_panel":("Suggestions","sugestao_admin"),"log_channel":("AuditPanel","logs_canal")}
CALLS={
 "queue":("SuggestionQueue","sugestao_fila"),"team":("SuggestionTeam","sugestao_equipe"),
 "metrics":("MetricsCog","metricas"),"report":("MetricsCog","relatorio"),
 "appearance":("AppearanceCog","personalize"),"history":("AuditPanel","historico",None),
 "antispam":("AntispamSettings","antispam"),"dm_config":("DmSettings","config_dms"),
 "discussion_config":("DiscussionSettings","config"),
 "activities":("ActivityCog","atividades"),"maintenance_panel":("Maintenance","painel"),
 "anon_on":("Suggestions","sugestao_anonimato",True),"anon_off":("Suggestions","sugestao_anonimato",False),
}


def home_embed():
    return discord.Embed(title="💡 KING PLUS — Sugestões",description="Gerenciamento completo de sugestões\n\n**Armazenamento:** JSON  •  **Acesso:** Admin",color=discord.Color.blurple())


class Section(discord.ui.View):
    def __init__(self, section):
        super().__init__(timeout=240)
        for j,(label,action) in enumerate(SECTIONS[section][1]):
            self.add_item(ActionButton(label,action,row=j//5))
        self.add_item(ActionButton("← Voltar","back",row=3))
        self.add_item(ActionButton("⌂ Principal","home",row=3))


class Home(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=240)
        for j,(action,label) in enumerate([("painel","Criar Painel"),("sugestoes","Sugestões"),("equipe","Equipe"),("votos","Votações"),("logs","Logs"),("config","Configurações"),("stats","Estatísticas"),("maintenance","Manutenção")]):
            self.add_item(ActionButton(label,action,row=j//2,style=discord.ButtonStyle.primary if j==0 else discord.ButtonStyle.secondary))


class UnifiedSuggestions(commands.Cog):
    def __init__(self,bot):self.bot=bot
    @app_commands.command(name="sugestao",description="Abre o painel principal de sugestões KING PLUS")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def painel(self,i:discord.Interaction):
        await i.response.send_message(embed=home_embed(),view=Home(),ephemeral=True)


async def setup(bot):
    await bot.add_cog(UnifiedSuggestions(bot))
