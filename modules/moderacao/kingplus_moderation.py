import asyncio
import io
import json
import re
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands
from .storage import load, save

FEATURES = ['base', 'punishments', 'warnings', 'policy', 'channels', 'spam', 'links', 'words', 'attachments', 'scam', 'raid', 'logs', 'appearance', 'security', 'statistics', 'maintenance']
NAMES = ['Base e painel', 'Punições', 'Advertências', 'Política de punições', 'Canais', 'Anti-Spam', 'Anti-Links', 'Palavras proibidas', 'Anexos', 'Anti-Scam', 'Anti-Raid', 'Logs', 'Aparência', 'Segurança', 'Estatísticas', 'Manutenção']


def permitted(member, data):
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    role_id = data.get('staff_role')
    return bool(role_id and any(r.id == role_id for r in member.roles))


class ValueModal(discord.ui.Modal):
    def __init__(self, cog, action, title, label, placeholder=''):
        super().__init__(title=title[:45])
        self.cog, self.action = cog, action
        self.value = discord.ui.TextInput(label=label[:45], placeholder=placeholder[:100], max_length=400)
        self.add_item(self.value)

    async def on_submit(self, interaction):
        await self.cog.apply(interaction, self.action, str(self.value.value).strip())


class ActionButton(discord.ui.Button):
    def __init__(self, cog, action, title, row=0, style=discord.ButtonStyle.secondary):
        super().__init__(label=title[:80], style=style, row=row, custom_id=f'kpmod:{action}')
        self.cog, self.action = cog, action

    async def callback(self, interaction):
        await self.cog.action(interaction, self.action)


class Panel(discord.ui.View):
    def __init__(self, cog, page='home'):
        super().__init__(timeout=None)
        self.cog = cog
        if page == 'home':
            entries = [('punishments','Moderação'), ('warnings','Advertências'), ('policy','Políticas'), ('channels','Canais'), ('spam','Anti-Spam'), ('links','Anti-Links'), ('words','Palavras'), ('attachments','Anexos'), ('scam','Anti-Scam'), ('raid','Anti-Raid'), ('logs','Logs'), ('appearance','Aparência'), ('security','Segurança'), ('statistics','Estatísticas'), ('maintenance','Manutenção')]
            entries = [(key, label) for key, label in entries if key in FEATURES]
            # Discord permite até 25 botões e 5 linhas de 5.
            for index, (key, label) in enumerate(entries):
                self.add_item(ActionButton(cog, f'page:{key}', label, row=index//5))
        else:
            actions = {
                'punishments':[('ban','Banir'),('kick','Expulsar'),('timeout','Timeout 10 min'),('untimeout','Remover timeout')],
                'warnings':[('warn','Advertir'),('warnlist','Consultar avisos'),('clearwarn','Limpar avisos')],
                'policy':[('policy_limit','Limite de avisos'),('policy_timeout','Timeout automático')],
                'channels':[('lock','Bloquear canal'),('unlock','Desbloquear canal'),('purge','Limpar mensagens')],
                'spam':[('toggle_spam','Ativar/desativar'),('spam_limit','Limite de mensagens')],
                'links':[('toggle_links','Ativar/desativar')],
                'words':[('addword','Adicionar palavra'),('delword','Remover palavra'),('listwords','Listar palavras')],
                'attachments':[('toggle_attachments','Ativar/desativar')],
                'scam':[('toggle_scam','Ativar/desativar')],
                'raid':[('toggle_raid','Ativar/desativar'),('raid_limit','Limite de entradas')],
                'logs':[('log_channel','Definir canal de logs'),('recent_cases','Últimos casos')],
                'appearance':[('panel_title','Título do painel')],
                'security':[('staff_role','Cargo da equipe'),('toggle_system','Ativar/desativar sistema')],
                'statistics':[('stats','Ver estatísticas')],
                'maintenance':[('diagnostic','Diagnóstico'),('backup','Exportar backup JSON')],
            }
            for i,(key,label) in enumerate(actions.get(page, [])):
                self.add_item(ActionButton(cog, key, label, row=i//5))
            self.add_item(ActionButton(cog, 'home', '← Voltar', row=4))


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam_window = defaultdict(deque)
        self.join_window = defaultdict(deque)

    @app_commands.command(name='moderacao', description='Abre o painel KING PLUS Moderação & AutoMod')
    @app_commands.guild_only()
    async def moderacao(self, interaction: discord.Interaction):
        data = load(interaction.guild_id)
        if not permitted(interaction.user, data):
            return await interaction.response.send_message('Sem permissão para acessar o painel.', ephemeral=True)
        await self.render(interaction, 'home', first=True)

    async def render(self, interaction, page, first=False):
        data = load(interaction.guild_id)
        title = data['settings'].get('panel_title', 'KING PLUS — Moderação & AutoMod')
        embed = discord.Embed(title=title if page == 'home' else f'{title} | {page.title()}', description='Gerencie a moderação por botões e formulários.\nArmazenamento: JSON • Acesso: Equipe autorizada', color=discord.Color.blurple())
        if first: await interaction.response.send_message(embed=embed, view=Panel(self, page), ephemeral=True)
        else: await interaction.response.edit_message(embed=embed, view=Panel(self, page))

    async def log(self, guild, text):
        data = load(guild.id)
        channel = guild.get_channel(data.get('log_channel') or 0)
        if channel:
            try: await channel.send(text[:1900], allowed_mentions=discord.AllowedMentions.none())
            except discord.DiscordException: pass

    async def record(self, guild, actor, target, kind, reason):
        data = load(guild.id)
        case = {'id':len(data['cases'])+1,'type':kind,'actor':actor,'target':target,'reason':reason,'time':int(time.time())}
        data['cases'].append(case)
        data['cases'] = data['cases'][-2000:]
        data['counters'][kind] = data['counters'].get(kind,0)+1
        save(guild.id,data)
        await self.log(guild,f'Caso #{case["id"]}: {kind} | alvo {target} | responsável {actor} | {reason}')

    async def action(self, interaction, action):
        data = load(interaction.guild_id)
        if not permitted(interaction.user, data):
            return await interaction.response.send_message('Sem permissão.',ephemeral=True)
        if action == 'home': return await self.render(interaction, 'home')
        if action.startswith('page:'): return await self.render(interaction, action.split(':',1)[1])
        if action in ('toggle_spam','toggle_links','toggle_attachments','toggle_scam','toggle_raid','toggle_system'):
            key = action.replace('toggle_','')
            if key == 'system': data['enabled'] = not data['enabled']; enabled=data['enabled']
            else:
                key = 'filter_'+key
                enabled = not data['settings'].get(key,False)
                data['settings'][key]=enabled
            save(interaction.guild_id,data)
            return await interaction.response.send_message(f'{action}: {"ativado" if enabled else "desativado"}.',ephemeral=True)
        if action in ('stats','diagnostic','recent_cases','listwords','warnlist','backup'):
            if action=='backup':
                payload=json.dumps(data,ensure_ascii=False,indent=2).encode()
                return await interaction.response.send_message(file=discord.File(io.BytesIO(payload),filename=f'moderacao_{interaction.guild_id}.json'),ephemeral=True)
            if action=='stats': result=json.dumps(data['counters'],ensure_ascii=False,indent=2)
            elif action=='diagnostic': result=f'JSON válido. Casos: {len(data["cases"])}. Filtros: {len(data["settings"])}.'
            elif action=='recent_cases': result=json.dumps(data['cases'][-10:],ensure_ascii=False,indent=2)
            elif action=='listwords': result=', '.join(data['settings'].get('bad_words',[])) or 'Nenhuma palavra cadastrada.'
            else: result='Para consultar avisos, use o botão e informe o ID do membro.'
            if action!='warnlist': return await interaction.response.send_message(f'```{str(result)[:1750]}```',ephemeral=True)
        labels={'ban':'ID do membro e motivo (ID | motivo)','kick':'ID do membro e motivo (ID | motivo)','timeout':'ID do membro e motivo (ID | motivo)','untimeout':'ID do membro','warn':'ID do membro e motivo (ID | motivo)','warnlist':'ID do membro','clearwarn':'ID do membro','policy_limit':'Quantidade de advertências','policy_timeout':'Minutos de timeout','lock':'ID do canal (vazio não permitido)','unlock':'ID do canal','purge':'Quantidade (1 a 100)','spam_limit':'Mensagens em 8 segundos','addword':'Palavra proibida','delword':'Palavra a remover','raid_limit':'Entradas em 15 segundos','log_channel':'ID do canal','panel_title':'Título','staff_role':'ID do cargo'}
        if action in labels:
            return await interaction.response.send_modal(ValueModal(self,action,action.replace('_',' ').title(),labels[action]))
        await interaction.response.send_message('Ação não disponível nesta fase.',ephemeral=True)

    async def apply(self, interaction, action, value):
        data=load(interaction.guild_id)
        if not permitted(interaction.user,data): return await interaction.response.send_message('Sem permissão.',ephemeral=True)
        guild=interaction.guild
        try:
            if action in ('ban','kick','timeout','untimeout','warn','warnlist','clearwarn'):
                user_id,_,reason=value.partition('|'); uid=int(user_id.strip()); reason=reason.strip() or 'Sem motivo informado'
                if action in ('warnlist','clearwarn'):
                    count=len(data['warnings'].get(str(uid),[]))
                    if action=='clearwarn': data['warnings'].pop(str(uid),None);save(guild.id,data)
                    return await interaction.response.send_message(f'Avisos de {uid}: {count}'+(' (limpos)' if action=='clearwarn' else ''),ephemeral=True)
                if action=='warn':
                    data['warnings'].setdefault(str(uid),[]).append({'by':interaction.user.id,'reason':reason,'at':int(time.time())})
                    save(guild.id,data)
                    await self.record(guild,interaction.user.id,uid,'warn',reason)
                    limit=data['settings'].get('policy_limit',0)
                    if limit and len(data['warnings'][str(uid)])>=limit:
                        member=guild.get_member(uid)
                        if member and guild.me.guild_permissions.moderate_members and member.top_role < guild.me.top_role:
                            minutes=data['settings'].get('policy_timeout',10)
                            await member.timeout(timedelta(minutes=minutes),reason='Limite de advertências')
                    return await interaction.response.send_message('Advertência registrada.',ephemeral=True)
                member=await guild.fetch_member(uid) if action!='ban' else None
                if action=='ban':
                    if not interaction.user.guild_permissions.ban_members: raise PermissionError('Você precisa de Banir Membros.')
                    await guild.ban(discord.Object(id=uid),reason=reason)
                elif action=='kick':
                    if not interaction.user.guild_permissions.kick_members: raise PermissionError('Você precisa de Expulsar Membros.')
                    await member.kick(reason=reason)
                else:
                    if not interaction.user.guild_permissions.moderate_members: raise PermissionError('Você precisa de Moderar Membros.')
                    await member.timeout(timedelta(minutes=10) if action=='timeout' else None,reason=reason)
                await self.record(guild,interaction.user.id,uid,action,reason)
                return await interaction.response.send_message('Ação concluída.',ephemeral=True)
            if action in ('lock','unlock'):
                if not interaction.user.guild_permissions.manage_channels: raise PermissionError('Gerenciar Canais necessário.')
                channel=guild.get_channel(int(value)); assert isinstance(channel,discord.TextChannel),'Canal de texto não encontrado'
                await channel.set_permissions(guild.default_role,send_messages=(False if action=='lock' else None),reason=f'KING PLUS por {interaction.user}')
            elif action=='purge':
                if not interaction.user.guild_permissions.manage_messages: raise PermissionError('Gerenciar Mensagens necessário.')
                n=int(value); assert 1<=n<=100,'Use 1 a 100'
                await interaction.channel.purge(limit=n)
            elif action in ('policy_limit','policy_timeout','spam_limit','raid_limit'):
                number=int(value); assert 1<=number<=10080,'Valor fora do intervalo'
                data['settings'][action]=number;save(guild.id,data)
            elif action in ('addword','delword'):
                word=value.lower().strip();assert 2<=len(word)<=100,'Palavra inválida'
                words=data['settings'].setdefault('bad_words',[])
                if action=='addword' and word not in words: words.append(word)
                if action=='delword' and word in words: words.remove(word)
                save(guild.id,data)
            elif action in ('log_channel','staff_role'):
                ident=int(value)
                if action=='log_channel': assert guild.get_channel(ident),'Canal inexistente';data['log_channel']=ident
                else: assert guild.get_role(ident),'Cargo inexistente';data['staff_role']=ident
                save(guild.id,data)
            elif action=='panel_title':
                assert 1<=len(value)<=100,'Título inválido'
                data['settings']['panel_title']=value;save(guild.id,data)
            else: raise ValueError('Ação desconhecida')
            await interaction.response.send_message('Configuração aplicada.',ephemeral=True)
        except (ValueError,AssertionError,PermissionError,discord.DiscordException) as exc:
            await interaction.response.send_message(f'Não foi possível executar: {str(exc)[:400]}',ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self,message):
        if not message.guild or message.author.bot: return
        data=load(message.guild.id)
        if not data['enabled'] or message.author.guild_permissions.manage_messages: return
        settings=data['settings'];content=message.content.lower(); reason=None
        if 'words' in FEATURES and settings.get('bad_words') and any(re.search(r'(?<!\w)'+re.escape(w)+r'(?!\w)',content) for w in settings['bad_words']): reason='Palavra proibida'
        if 'links' in FEATURES and settings.get('filter_links') and re.search(r'https?://|www\.',content): reason='Links bloqueados'
        if 'attachments' in FEATURES and settings.get('filter_attachments') and message.attachments: reason='Anexos bloqueados'
        if 'scam' in FEATURES and settings.get('filter_scam') and re.search(r'(free nitro|discord\.gift|steamcommunity\.com\.[a-z]+)',content): reason='Possível golpe'
        if 'spam' in FEATURES and settings.get('filter_spam'):
            key=(message.guild.id,message.author.id);q=self.spam_window[key];now=time.monotonic();q.append(now)
            while q and now-q[0]>8:q.popleft()
            if len(q)>=settings.get('spam_limit',6):reason='Spam'
        if reason:
            try:
                await message.delete()
                await self.record(message.guild,self.bot.user.id,message.author.id,'automod',reason)
            except discord.DiscordException: pass

    @commands.Cog.listener()
    async def on_member_join(self,member):
        if 'raid' not in FEATURES:return
        data=load(member.guild.id)
        if not data['enabled'] or not data['settings'].get('filter_raid'):return
        q=self.join_window[member.guild.id];now=time.monotonic();q.append(now)
        while q and now-q[0]>15:q.popleft()
        if len(q)>=data['settings'].get('raid_limit',8):
            await self.log(member.guild,f'⚠️ Anti-Raid: {len(q)} entradas em 15 segundos. Verifique o servidor.')


async def setup(bot):
    await bot.add_cog(Moderation(bot))
