"""Central de níveis: somente /nivel e /perfil são comandos registrados."""
import discord
from .admin_panel import XPModal, MessageModal, RewardModal, ChannelView
from ..announcements import DEFAULT_MESSAGE, render_announcement
from ..cards.rank_card import THEMES


def admin(interaction, owner):
    return (interaction.guild is not None and interaction.user.id == owner
            and interaction.user.guild_permissions.manage_guild)


class FilterModal(discord.ui.Modal):
    ident = discord.ui.TextInput(label="ID do canal ou cargo", max_length=22)
    action = discord.ui.TextInput(label="Digite IGNORAR ou LIBERAR", max_length=7)
    def __init__(self, cog, kind):
        super().__init__(title=f"Filtro de {kind}")
        self.cog, self.kind = cog, kind
    async def on_submit(self, interaction):
        try:
            ident = int(self.ident.value.strip())
            action = self.action.value.strip().upper()
            if action not in ('IGNORAR', 'LIBERAR'): raise ValueError
        except ValueError:
            return await interaction.response.send_message("ID ou ação inválida.", ephemeral=True)
        obj = interaction.guild.get_channel(ident) if self.kind == 'canal' else interaction.guild.get_role(ident)
        if obj is None:
            return await interaction.response.send_message("Canal/cargo não encontrado neste servidor.", ephemeral=True)
        key = 'ignored_channel_ids' if self.kind == 'canal' else 'ignored_role_ids'
        cfg = (await self.cog.storage.get(interaction.guild_id))['config']
        ids = set(cfg.get(key, []))
        if action == 'IGNORAR': ids.add(ident)
        else: ids.discard(ident)
        await self.cog.storage.update_config(interaction.guild_id, **{key: sorted(ids)})
        await interaction.response.send_message("Filtro atualizado no JSON.", ephemeral=True)


class LevelModal(discord.ui.Modal):
    level = discord.ui.TextInput(label="Nível da recompensa a remover", max_length=5)
    def __init__(self, cog):
        super().__init__(title="Remover recompensa"); self.cog = cog
    async def on_submit(self, interaction):
        try: n = int(self.level.value)
        except ValueError: return await interaction.response.send_message("Nível inválido.", ephemeral=True)
        cfg = (await self.cog.storage.get(interaction.guild_id))['config']
        rewards = dict(cfg.get('rewards', {}))
        rewards.pop(str(n), None)
        await self.cog.storage.update_config(interaction.guild_id, rewards=rewards)
        await interaction.response.send_message("Recompensa removida, se existia.", ephemeral=True)


class RestoreModal(discord.ui.Modal):
    filename = discord.ui.TextInput(label="Nome exato do arquivo de backup", max_length=180)
    confirmation = discord.ui.TextInput(label="Digite RESTAURAR para confirmar", max_length=9)
    def __init__(self, cog):
        super().__init__(title="Restaurar backup JSON"); self.cog = cog
    async def on_submit(self, interaction):
        if self.confirmation.value != 'RESTAURAR':
            return await interaction.response.send_message("Restauração cancelada.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            safe = await self.cog.backups.restore(interaction.guild_id, self.filename.value.strip())
        except (ValueError, FileNotFoundError, OSError) as exc:
            return await interaction.followup.send(f"Falha: {exc}", ephemeral=True)
        await interaction.followup.send(f"Dados restaurados. Backup anterior: `{safe}`", ephemeral=True)


class ThemeSelect(discord.ui.Select):
    def __init__(self, cog):
        self.cog = cog
        super().__init__(placeholder="Tema do cartão", options=[discord.SelectOption(label=x.title(), value=x) for x in THEMES])
    async def callback(self, interaction):
        await self.cog.storage.update_config(interaction.guild_id, rank_theme=self.values[0])
        await interaction.response.send_message("Tema salvo em JSON.", ephemeral=True)


class ThemeView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=180); self.add_item(ThemeSelect(cog))


class AccentModal(discord.ui.Modal):
    color = discord.ui.TextInput(label="Cor hexadecimal, exemplo #7289DA", max_length=7)
    def __init__(self, cog):
        super().__init__(title="Cor do cartão"); self.cog = cog
    async def on_submit(self, interaction):
        import re
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', self.color.value.strip()):
            return await interaction.response.send_message("Use #RRGGBB.", ephemeral=True)
        await self.cog.storage.update_config(interaction.guild_id, rank_accent=self.color.value.strip())
        await interaction.response.send_message("Cor atualizada.", ephemeral=True)


class MainPanel(discord.ui.View):
    def __init__(self, cog, owner_id, page='main'):
        super().__init__(timeout=600)
        self.cog, self.owner_id, self.page = cog, owner_id, page
        self._build()

    async def interaction_check(self, interaction):
        if not admin(interaction, self.owner_id):
            await interaction.response.send_message("Apenas o administrador que abriu /nivel pode usar este painel.", ephemeral=True)
            return False
        return True

    async def embed(self, interaction):
        cfg = (await self.cog.storage.get(interaction.guild_id))['config']
        titles = {'main':'KING PLUS — Níveis', 'xp':'Configurar XP', 'filters':'Canais e Cargos',
                  'rewards':'Recompensas', 'announcements':'Avisos de Nível', 'ranking':'Ranking',
                  'appearance':'Personalização', 'stats':'Estatísticas', 'maintenance':'Manutenção'}
        e = discord.Embed(title='🏆 ' + titles[self.page], description='Gerenciamento completo de XP, níveis e recompensas', color=discord.Color.blurple())
        if self.page == 'main':
            e.add_field(name='Estado', value='🟢 Ativo' if cfg['enabled'] else '🔴 Desativado')
            e.add_field(name='XP', value=f"{cfg['xp_per_message_min']}–{cfg['xp_per_message_max']} / {cfg['cooldown_seconds']}s")
            e.add_field(name='Recompensas', value=str(len(cfg.get('rewards', {}))))
        elif self.page == 'filters':
            e.description = f"Canais ignorados: {len(cfg.get('ignored_channel_ids', []))}\nCargos ignorados: {len(cfg.get('ignored_role_ids', []))}"
        elif self.page == 'rewards':
            e.description = 'Modo: ' + cfg.get('reward_mode','stack') + '\n' + ('\n'.join(f'Nível {n}: <@&{r}>' for n,r in cfg.get('rewards', {}).items())[:1500] or 'Sem recompensas')
        elif self.page == 'announcements':
            e.description = 'Avisos: ' + ('Ativos' if cfg.get('announce_level_up') else 'Desativados')
        elif self.page == 'appearance':
            e.description = f"Tema: {cfg.get('rank_theme','dark')}\nCor: {cfg.get('rank_accent') or 'padrão'}"
        elif self.page == 'stats':
            data = await self.cog.storage.get(interaction.guild_id)
            members = data.get('members', {})
            e.description = f"Membros registrados: {len(members)}\nXP acumulado: {sum(int(m.get('xp',0)) for m in members.values()):,}"
        elif self.page == 'maintenance':
            e.description = 'Backups, restauração e ativação/desativação do sistema.'
        e.set_footer(text='Armazenamento: JSON • Admin • /nivel e /perfil')
        return e

    def _add(self, label, callback, row, style=discord.ButtonStyle.secondary):
        button = discord.ui.Button(label=label, style=style, row=row)
        button.callback = callback
        self.add_item(button)

    async def _nav(self, interaction, page):
        new = MainPanel(self.cog, self.owner_id, page)
        await interaction.response.edit_message(embed=await new.embed(interaction), view=new)

    def _build(self):
        if self.page == 'main':
            entries = [('Configurar XP','xp'), ('Canais e Cargos','filters'), ('Recompensas','rewards'),
                       ('Avisos de Nível','announcements'), ('Ranking','ranking'), ('Personalização','appearance'),
                       ('Estatísticas','stats'), ('Manutenção','maintenance')]
            for idx,(label,page) in enumerate(entries):
                async def go(interaction, p=page): await self._nav(interaction,p)
                self._add(label,go,idx//2,discord.ButtonStyle.primary if idx==0 else discord.ButtonStyle.secondary)
        else:
            actions = {
                'xp':[('Configurar XP',self._xp)],
                'filters':[('Ignorar/Liberar Canal',self._channel_filter),('Ignorar/Liberar Cargo',self._role_filter)],
                'rewards':[('Adicionar',self._reward),('Remover',self._remove_reward),('Alternar modo',self._reward_mode)],
                'announcements':[('Ativar/Desativar',self._toggle_ann),('Editar mensagem',self._message),('Canal de avisos',self._channel),('Prévia',self._preview)],
                'ranking':[('Ver ranking',self._ranking)],
                'appearance':[('Escolher tema',self._theme),('Definir cor',self._accent),('Prévia do cartão',self._card)],
                'stats':[('Atualizar',self._refresh)],
                'maintenance':[('Ativar/Desativar XP',self._toggle),('Criar backup',self._backup),('Listar backups',self._backups),('Restaurar',self._restore)]
            }
            for idx,(label,cb) in enumerate(actions[self.page]): self._add(label,cb,idx//2)
        self._add('← Voltar',self._back,4)
        self._add('⌂ Central',self._home,4)

    async def _back(self,i): await self._nav(i,'main')
    async def _home(self,i): await self._nav(i,'main')
    async def _refresh(self,i): await i.response.edit_message(embed=await self.embed(i),view=self)
    async def _xp(self,i): await i.response.send_modal(XPModal(self.cog))
    async def _channel_filter(self,i): await i.response.send_modal(FilterModal(self.cog,'canal'))
    async def _role_filter(self,i): await i.response.send_modal(FilterModal(self.cog,'cargo'))
    async def _reward(self,i): await i.response.send_modal(RewardModal(self.cog))
    async def _remove_reward(self,i): await i.response.send_modal(LevelModal(self.cog))
    async def _reward_mode(self,i):
        cfg=(await self.cog.storage.get(i.guild_id))['config']
        mode='replace' if cfg.get('reward_mode')=='stack' else 'stack'
        await self.cog.storage.update_config(i.guild_id,reward_mode=mode)
        await i.response.edit_message(embed=await self.embed(i),view=self)
    async def _toggle_ann(self,i):
        cfg=(await self.cog.storage.get(i.guild_id))['config']
        await self.cog.storage.update_config(i.guild_id,announce_level_up=not cfg['announce_level_up'])
        await i.response.edit_message(embed=await self.embed(i),view=self)
    async def _message(self,i):
        cfg=(await self.cog.storage.get(i.guild_id))['config']
        await i.response.send_modal(MessageModal(self.cog,cfg.get('level_up_message',DEFAULT_MESSAGE)))
    async def _channel(self,i): await i.response.send_message('Escolha o canal:',view=ChannelView(self.cog),ephemeral=True)
    async def _preview(self,i):
        cfg=(await self.cog.storage.get(i.guild_id))['config']
        msg=render_announcement(cfg.get('level_up_message',DEFAULT_MESSAGE),member_name=i.user.display_name,member_id=i.user.id,level=10,previous_level=9,guild_name=i.guild.name)
        await i.response.send_message(msg,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    async def _ranking(self,i): await self.cog.ranking(i)
    async def _theme(self,i): await i.response.send_message('Selecione o tema:',view=ThemeView(self.cog),ephemeral=True)
    async def _accent(self,i): await i.response.send_modal(AccentModal(self.cog))
    async def _card(self,i): await self.cog._send_rank_card(i,i.user)
    async def _toggle(self,i):
        cfg=(await self.cog.storage.get(i.guild_id))['config']
        await self.cog.storage.update_config(i.guild_id,enabled=not cfg['enabled'])
        await i.response.edit_message(embed=await self.embed(i),view=self)
    async def _backup(self,i): await self.cog.backup(i)
    async def _backups(self,i): await self.cog.backups_list(i)
    async def _restore(self,i): await i.response.send_modal(RestoreModal(self.cog))
