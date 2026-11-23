import os
import discord
from discord import app_commands
from discord.ext import commands
from core.maintenance_notices import save_notice_channel, notice_channel_id, send_maintenance_notice, save_setting
from core.audit_log import audit

OWNER_ID = int(os.getenv('OWNER_ID', '0'))


def make_embed(manager):
    embed = discord.Embed(title='⚙️ Controle Central de Sistemas', description=manager.status_text() + '\n\n🔒 Somente dono do bot', color=discord.Color.blurple())
    embed.set_footer(text='KING PLUS • Controle Central • Fase 8')
    return embed


class SystemButton(discord.ui.Button):
    def __init__(self, key, system, index):
        enabled = system['enabled']
        super().__init__(label=f"{'Desativar' if enabled else 'Ativar'} {system['name']}", emoji=system['emoji'], style=discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success, row=index // 5, custom_id=f'kingplus:system:{key}')
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message('⛔ Apenas o dono pode usar este painel.', ephemeral=True)
            return
        manager = interaction.client.system_manager
        current = manager.is_enabled(self.key)
        name = manager.systems[self.key]['name']
        action = 'desativar' if current else 'ativar'
        await interaction.response.send_message(f'Confirma **{action}** o sistema **{name}**?', view=ConfirmView(self.key, current), ephemeral=True)


class ConfirmView(discord.ui.View):
    def __init__(self, key: str, expected_enabled: bool):
        super().__init__(timeout=120)
        self.key = key
        self.expected_enabled = expected_enabled

    async def interaction_check(self, interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message('⛔ Acesso negado.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Confirmar', style=discord.ButtonStyle.danger, emoji='✅')
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        manager = interaction.client.system_manager
        # Confirmação é vinculada ao estado apresentado: evita ação inversa acidental.
        async with manager._lock:
            if manager.is_enabled(self.key) != self.expected_enabled:
                await interaction.response.edit_message(content='⚠️ O estado mudou. Abra /sistemas novamente.', view=None)
                return
            try:
                await manager._set_enabled_unlocked(self.key, not self.expected_enabled)
            except Exception:
                await interaction.response.edit_message(content='❌ Falha ao salvar. Tente novamente.', view=None)
                raise
        try:
            await audit(interaction.client, 'system_state_changed', interaction.user.id,
                        system=self.key, previous=self.expected_enabled,
                        current=not self.expected_enabled)
        except OSError:
            # A mudança já foi persistida: não esconder seu resultado.
            pass
        await interaction.response.defer()
        published, notice_detail = await send_maintenance_notice(interaction.client, self.key, not self.expected_enabled, interaction.user)
        status = 'ativado com sucesso' if not self.expected_enabled else 'desativado para manutenção'
        await interaction.edit_original_response(content=f'✅ Sistema **{manager.systems[self.key]["name"]}** {status}. Abra `/sistemas` para ver o painel atualizado.\n📢 {notice_detail if published else '⚠️ ' + notice_detail}', view=None)
        await update_published_panel(interaction.client)
        self.stop()

    @discord.ui.button(label='Cancelar', style=discord.ButtonStyle.secondary, emoji='✖️')
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content='Operação cancelada. Nenhum estado foi alterado.', view=None)
        self.stop()


class SystemsView(discord.ui.View):
    def __init__(self, manager, persistent=False):
        super().__init__(timeout=None if persistent else 900)
        if len(manager.systems) > 20:
            raise ValueError('O painel suporta até 20 sistemas nesta versão.')
        for index, (key, system) in enumerate(manager.systems.items()):
            self.add_item(SystemButton(key, system, index))

    @discord.ui.button(label='Atualizar', style=discord.ButtonStyle.secondary, emoji='🔄', row=4)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message('⛔ Acesso negado.', ephemeral=True)
            return
        manager = interaction.client.system_manager
        await interaction.response.edit_message(embed=make_embed(manager), view=SystemsView(manager, persistent=not interaction.message.flags.ephemeral))


async def update_published_panel(bot):
    """Atualiza a mensagem pública registrada, sem publicar mensagens duplicadas."""
    from core.maintenance_notices import get_setting
    channel_id = get_setting('panel_channel_id')
    message_id = get_setting('panel_message_id')
    if not channel_id or not message_id:
        return False
    try:
        channel = bot.get_channel(int(channel_id)) or await bot.fetch_channel(int(channel_id))
        message = await channel.fetch_message(int(message_id))
        await message.edit(embed=make_embed(bot.system_manager), view=SystemsView(bot.system_manager, persistent=True))
        return True
    except (discord.HTTPException, discord.Forbidden, discord.NotFound, ValueError, AttributeError):
        return False


class SystemsPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='publicar_painel_sistemas', description='Publica painel persistente em um canal')
    @app_commands.describe(canal='Canal onde o painel administrativo será publicado')
    async def publicar_painel_sistemas(self, interaction: discord.Interaction, canal: discord.TextChannel):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message('⛔ Acesso negado.', ephemeral=True)
            return
        if not interaction.guild or canal.guild.id != interaction.guild.id:
            await interaction.response.send_message('❌ Escolha um canal deste servidor.', ephemeral=True)
            return
        me = interaction.guild.me
        perms = canal.permissions_for(me)
        if not (perms.view_channel and perms.send_messages and perms.embed_links and perms.read_message_history):
            await interaction.response.send_message('❌ Preciso ver o canal, enviar mensagens, inserir links e ler histórico.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        old_channel = __import__('core.maintenance_notices', fromlist=['get_setting']).get_setting('panel_channel_id')
        old_message = __import__('core.maintenance_notices', fromlist=['get_setting']).get_setting('panel_message_id')
        if old_channel and old_message:
            try:
                previous_channel = self.bot.get_channel(int(old_channel)) or await self.bot.fetch_channel(int(old_channel))
                previous = await previous_channel.fetch_message(int(old_message))
                await previous.edit(view=None)
            except (discord.HTTPException, discord.Forbidden, discord.NotFound, ValueError, AttributeError):
                pass
        message = await canal.send(embed=make_embed(self.bot.system_manager), view=SystemsView(self.bot.system_manager, persistent=True))
        save_setting('panel_channel_id', canal.id)
        save_setting('panel_message_id', message.id)
        await interaction.followup.send(f'✅ Painel persistente publicado: {message.jump_url}', ephemeral=True)

    @app_commands.command(name='canal_avisos' , description='Define o canal de avisos de manutenção')
    @app_commands.describe(canal='Canal que receberá avisos de manutenção')
    async def canal_avisos(self, interaction: discord.Interaction, canal: discord.TextChannel):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message('⛔ Apenas o dono pode configurar avisos.', ephemeral=True)
            return
        me = interaction.guild.me if interaction.guild else None
        if me is None or not canal.permissions_for(me).send_messages or not canal.permissions_for(me).embed_links:
            await interaction.response.send_message('❌ Preciso das permissões Enviar Mensagens e Inserir Links neste canal.', ephemeral=True)
            return
        save_notice_channel(canal.id)
        try:
            await audit(self.bot, 'notice_channel_changed', interaction.user.id, detail=f'channel_id={canal.id}')
        except OSError:
            pass
        await interaction.response.send_message(f'📢 Canal de manutenção configurado: {canal.mention}', ephemeral=True)

    @app_commands.command(name='canal_logs', description='Configura o canal de auditoria do KING PLUS')
    @app_commands.describe(canal='Canal privado para os logs administrativos')
    async def canal_logs(self, interaction: discord.Interaction, canal: discord.TextChannel):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message('⛔ Acesso negado.', ephemeral=True)
            return
        if not interaction.guild:
            await interaction.response.send_message('Use este comando no servidor.', ephemeral=True)
            return
        me = interaction.guild.me
        if me is None or not (canal.permissions_for(me).send_messages and canal.permissions_for(me).embed_links):
            await interaction.response.send_message('❌ Faltam permissões no canal.', ephemeral=True)
            return
        save_setting('audit_channel_id', canal.id)
        await interaction.response.send_message(f'🛡️ Canal de logs configurado: {canal.mention}', ephemeral=True)
        try:
            await audit(self.bot, 'audit_channel_changed', interaction.user.id, detail=f'channel_id={canal.id}')
        except OSError:
            pass

    @app_commands.command(name='logs_sistemas', description='Mostra os últimos registros do Controle Central')
    async def logs_sistemas(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message('⛔ Acesso negado.', ephemeral=True)
            return
        from core.audit_log import LOG_FILE
        from collections import deque
        import json
        if not LOG_FILE.exists():
            await interaction.response.send_message('Ainda não há registros.', ephemeral=True)
            return
        with LOG_FILE.open(encoding='utf-8') as fp:
            recent = deque(fp, maxlen=8)
        entries = [json.loads(line) for line in recent if line.strip()]
        lines = [f"`{e['at'][:16]}` • {e['action']} • {e.get('system') or '-'} • ID {e['actor_id']}" for e in entries]
        await interaction.response.send_message('🛡️ **Últimas ações**\n' + ('\n'.join(lines) or 'Nenhuma'), ephemeral=True)

    @app_commands.command(name='sistemas', description='Abre o Controle Central de Sistemas KING PLUS')
    async def sistemas(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message('⛔ Apenas o dono do bot pode acessar este painel.', ephemeral=True)
            return
        manager = self.bot.system_manager
        await interaction.response.send_message(embed=make_embed(manager), view=SystemsView(manager), ephemeral=True)


async def setup(bot):
    await bot.add_cog(SystemsPanel(bot))
