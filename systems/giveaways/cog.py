import discord
from discord import app_commands
from discord.ext import commands, tasks
from .storage.json_store import GiveawayStore
from .views.admin_panel import AdminPanel
from .views.participation import ParticipationView
from .views.appearance_panel import DEFAULTS, build_embed
import asyncio
import logging
import io
from .maintenance import inspect_store, export_guild, restore_guild
from datetime import datetime, timezone, timedelta

class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.store = GiveawayStore()
        self._message_locks = {}
        self._closing = asyncio.Lock()
        self._publishing = asyncio.Lock()

    def message_update_lock(self, message_id):
        return self._message_locks.setdefault(message_id, asyncio.Lock())

    async def cog_load(self):
        # Um único custom_id persistente atende todas as mensagens, inclusive após reiniciar.
        self.bot.add_view(ParticipationView(self))
        self.expiration_worker.start()
        self.schedule_worker.start()
        self.audit_worker.start()

    def cog_unload(self):
        self.expiration_worker.cancel()
        self.schedule_worker.cancel()
        self.audit_worker.cancel()

    async def sorteio_logs_canal(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message('❌ Requer Gerenciar Servidor.', ephemeral=True)
            return
        if canal and not canal.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message('❌ O bot não pode enviar mensagens nesse canal.', ephemeral=True)
            return
        await self.store.configure_audit_channel(interaction.guild_id, canal.id if canal else None)
        await interaction.response.send_message(
            f'✅ Canal de logs: {canal.mention}' if canal else '✅ Avisos de auditoria desativados. Histórico JSON mantido.', ephemeral=True)

    async def sorteio_historico(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message('❌ Requer Gerenciar Servidor.', ephemeral=True)
            return
        events = await self.store.audit_history(interaction.guild_id, 15)
        lines = [f"<t:{int(datetime.fromisoformat(e['at']).timestamp())}:f> • **{e['event']}**" +
                 (f" • ID `{e['reference']}`" if e.get('reference') else '') for e in events]
        await interaction.response.send_message('\n'.join(lines)[:1900] if lines else 'Nenhum evento registrado.', ephemeral=True)

    @tasks.loop(seconds=20)
    async def audit_worker(self):
        for guild_id, channel_id, event in await self.store.pending_audit():
            try:
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                message = f"📋 **KING PLUS • Auditoria de Sorteios**\nEvento: `{event['event']}`"
                if event.get('reference'):
                    message += f"\nReferência: `{event['reference']}`"
                message += f"\nData: <t:{int(datetime.fromisoformat(event['at']).timestamp())}:f>"
                await channel.send(message, allowed_mentions=discord.AllowedMentions.none())
                await self.store.mark_audit_delivered(guild_id, event['id'])
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                logging.warning('Falha ao enviar auditoria %s no servidor %s', event['id'], guild_id)
            except Exception:
                logging.exception('Falha inesperada ao enviar auditoria')

    @audit_worker.before_loop
    async def before_audit_worker(self):
        await self.bot.wait_until_ready()

    @staticmethod
    def eligibility_error(member, requirements):
        if not isinstance(member, discord.Member) or member.bot:
            return 'Apenas membros humanos do servidor podem participar.'
        role_id = requirements.get('role_id')
        if role_id and not any(role.id == int(role_id) for role in member.roles):
            return f'É necessário possuir o cargo <@&{role_id}>.'
        account_days = int(requirements.get('min_account_days', 0))
        if account_days and datetime.now(timezone.utc) - member.created_at < timedelta(days=account_days):
            return f'A conta Discord deve ter pelo menos {account_days} dia(s).'
        days = int(requirements.get('min_days', 0))
        if days and (not member.joined_at or datetime.now(timezone.utc) - member.joined_at < timedelta(days=days)):
            return f'É necessário estar no servidor há pelo menos {days} dia(s).'
        return None

    async def sorteio_requisitos(self, interaction: discord.Interaction, dias: app_commands.Range[int, 0, 365], cargo: discord.Role = None):
        await self.store.set_requirements(interaction.guild_id, cargo.id if cargo else None, dias)
        await interaction.response.send_message(
            f'✅ Requisitos dos próximos sorteios: cargo {cargo.mention if cargo else "nenhum"}; permanência mínima: {dias} dia(s).', ephemeral=True)

    async def sorteio_protecao(self, interaction: discord.Interaction, dias_conta: app_commands.Range[int, 0, 3650]):
        await self.store.set_account_age_requirement(interaction.guild_id, dias_conta)
        await interaction.response.send_message(
            f'🛡️ Idade mínima da conta nos próximos sorteios: {dias_conta} dia(s). 0 desativa.', ephemeral=True)

    async def filter_eligible(self, guild_id, message_id, record):
        """Revalida participantes antes de escolher vencedores."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        valid = []
        for uid in record.get('participants', []):
            member = guild.get_member(int(uid))
            if member is None:
                try:
                    member = await guild.fetch_member(int(uid))
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    continue
            if self.eligibility_error(member, record['requirements']) is None:
                valid.append(int(uid))
        await self.store.set_eligible_participants(guild_id, message_id, valid)

    async def eligible_ended(self, guild_id, record):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []
        valid = []
        for uid in record.get('participants', []):
            member = guild.get_member(int(uid))
            if member is None:
                try:
                    member = await guild.fetch_member(int(uid))
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    continue
            if self.eligibility_error(member, record.get('requirements') or {}) is None:
                valid.append(int(uid))
        return valid

    @tasks.loop(seconds=30)
    async def schedule_worker(self):
        async with self._publishing:
            now = datetime.now(timezone.utc)
            for guild_id, schedule in await self.store.pending_schedules(now.isoformat()):
                try:
                    channel = self.bot.get_channel(int(schedule['channel_id']))
                    if channel is None:
                        channel = await self.bot.fetch_channel(int(schedule['channel_id']))
                    ends = now + timedelta(seconds=int(schedule['duration_seconds']))
                    appearance = {**DEFAULTS, **schedule.get('appearance', {})}
                    embed = build_embed(schedule['prize'], schedule.get('description', ''), schedule['winner_count'], ends, appearance)
                    embed.add_field(name='Participantes', value='0', inline=True)
                    message = await channel.send(embed=embed, view=ParticipationView(self))
                    giveaway = {'message_id': message.id, 'guild_id': guild_id,
                                'channel_id': channel.id, 'host_id': schedule['host_id'],
                                'prize': schedule['prize'], 'description': schedule.get('description', ''),
                                'winner_count': schedule['winner_count'], 'created_at': now.isoformat(),
                                'ends_at': ends.isoformat(), 'status': 'active',
                                'participants': [], 'winners': [], 'requirements': schedule.get('requirements', {})}
                    try:
                        saved = await self.store.mark_schedule_published(guild_id, schedule['id'], giveaway)
                    except Exception:
                        logging.exception('Falha ao registrar publicação agendada %s', schedule['id'])
                        saved = False
                    if not saved:
                        try:
                            await message.delete()
                        except discord.HTTPException:
                            pass
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    logging.warning('Publicação agendada %s falhou; nova tentativa em 30 segundos.', schedule['id'])
                except Exception:
                    logging.exception('Erro no agendamento %s', schedule['id'])

    @schedule_worker.before_loop
    async def before_schedule_worker(self):
        await self.bot.wait_until_ready()

    async def sorteio_agendamentos(self, interaction: discord.Interaction):
        from .views.schedule_panel import show_schedule
        await show_schedule(interaction, self)

    async def sorteio_cancelar_agendamento(self, interaction: discord.Interaction, identificador: str):
        cancelled = await self.store.cancel_schedule(interaction.guild_id, identificador)
        await interaction.response.send_message('✅ Agendamento cancelado.' if cancelled else '❌ Agendamento não encontrado ou já publicado.', ephemeral=True)

    async def sorteio_cancelar_recorrente(self, interaction: discord.Interaction, identificador: str):
        cancelled = await self.store.cancel_recurring(interaction.guild_id, identificador)
        await interaction.response.send_message('✅ Recorrência cancelada.' if cancelled else '❌ Recorrência não encontrada.', ephemeral=True)

    @tasks.loop(seconds=30)
    async def expiration_worker(self):
        now = datetime.now(timezone.utc).isoformat()
        async with self._closing:
            for guild_id, message_id, _ in await self.store.expired_active(now):
                try:
                    record = await self.store.get_giveaway(guild_id, message_id)
                    if record:
                        await self.filter_eligible(guild_id, message_id, record)
                    await self.store.close_expired(guild_id, message_id, now)
                except Exception:
                    logging.exception('Falha ao encerrar sorteio %s', message_id)
            for guild_id, message_id, giveaway in await self.store.pending_announcements():
                try:
                    channel = self.bot.get_channel(int(giveaway['channel_id']))
                    if channel is None:
                        channel = await self.bot.fetch_channel(int(giveaway['channel_id']))
                    message = await channel.fetch_message(message_id)
                    embed = message.embeds[0].copy() if message.embeds else discord.Embed(title='🎁 Sorteio encerrado')
                    winners = giveaway.get('winners', [])
                    winner_text = ', '.join(f'<@{uid}>' for uid in winners) if winners else 'Nenhum participante elegível.'
                    if giveaway.get('reroll_history'):
                        winner_text += f'\n🔄 Rerolls realizados: {len(giveaway["reroll_history"])}'
                    index = next((i for i, field in enumerate(embed.fields) if field.name == '📌 Estado'), None)
                    if index is None:
                        embed.add_field(name='📌 Estado', value='🔒 Encerrado • resultado definido', inline=False)
                    else:
                        embed.set_field_at(index, name='📌 Estado', value='🔒 Encerrado • resultado definido', inline=False)
                    winner_index = next((i for i, field in enumerate(embed.fields) if field.name == '🏆 Vencedores'), None)
                    if winner_index is None:
                        embed.add_field(name='🏆 Vencedores', value=winner_text, inline=False)
                    else:
                        embed.set_field_at(winner_index, name='🏆 Vencedores', value=winner_text, inline=False)
                    await message.edit(embed=embed, view=None)
                    await self.store.mark_announced(guild_id, message_id)
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    logging.warning('Não foi possível atualizar a mensagem do sorteio %s. Tentaremos novamente.', message_id)
                except Exception:
                    logging.exception('Erro inesperado ao atualizar sorteio %s', message_id)

    @expiration_worker.before_loop
    async def before_expiration_worker(self):
        await self.bot.wait_until_ready()

    def make_panel_embed(self, config):
        embed = discord.Embed(
            title="🎉 KING PLUS • Central de Sorteios",
            description="Gerencie o sistema de sorteios pelos botões abaixo.\n\n**Painel único:** criação, gerenciamento, requisitos, logs, estatísticas e manutenção.",
            color=discord.Color.green() if config.get("enabled", True) else discord.Color.orange(),
        )
        embed.add_field(name="Estado", value="✅ Ativado" if config.get("enabled", True) else "🛠️ Em manutenção")
        embed.add_field(name="Armazenamento", value="JSON (sem SQLite)")
        embed.set_footer(text="KING PLUS • Sorteios cumulativos")
        return embed

    @app_commands.command(name="sorteio", description="Abre o painel administrativo de sorteios KING PLUS")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sorteio(self, interaction: discord.Interaction):
        config = await self.store.get_guild(interaction.guild_id)
        await interaction.response.send_message(embed=self.make_panel_embed(config), view=AdminPanel(self), ephemeral=True)

    async def sorteio_estatisticas(self, interaction: discord.Interaction):
        from .views.stats_panel import show_statistics
        await show_statistics(interaction, self)

    async def sorteio_diagnostico(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Requer Gerenciar Servidor.", ephemeral=True)
        result = inspect_store(self.store.path)
        summary = (f"{'✅' if result['ok'] else '⚠️'} **Diagnóstico KING PLUS**\n"
                   f"Servidores: {result['guilds']} | Sorteios: {result['giveaways']}\n"
                   f"Workers: expiração={self.expiration_worker.is_running()}, "
                   f"agendamento={self.schedule_worker.is_running()}, "
                   f"auditoria={self.audit_worker.is_running()}\n")
        if result['issues']:
            summary += "\n".join(result['issues'][:8])[:1200]
        await interaction.response.send_message(summary, ephemeral=True)

    async def sorteio_backup(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Requer Administrador.", ephemeral=True)
        content = await export_guild(self.store, interaction.guild_id)
        if len(content) > 8 * 1024 * 1024:
            return await interaction.response.send_message("Backup maior que 8 MB. Faça backup local do JSON.", ephemeral=True)
        await interaction.response.send_message("📦 Backup do servidor:", file=discord.File(io.BytesIO(content), filename=f"sorteios_{interaction.guild_id}.json"), ephemeral=True)

    async def sorteio_restaurar(self, interaction: discord.Interaction, arquivo: discord.Attachment, confirmar: bool):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Requer Administrador.", ephemeral=True)
        if not confirmar:
            return await interaction.response.send_message("Restauração cancelada. Use confirmar: verdadeiro para substituir os dados do servidor.", ephemeral=True)
        if not arquivo.filename.lower().endswith('.json') or arquivo.size > 8 * 1024 * 1024:
            return await interaction.response.send_message("Envie um JSON de até 8 MB.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            rollback = await restore_guild(self.store, interaction.guild_id, await arquivo.read())
        except (ValueError, OSError) as exc:
            return await interaction.followup.send(f"❌ {str(exc)[:1500]}", ephemeral=True)
        await interaction.followup.send(f"✅ Backup restaurado. Cópia anterior salva em `{rollback.name}`. Reinicie o bot para reconstruir os workers e mensagens persistentes.", ephemeral=True)

    async def sorteio_status(self, interaction: discord.Interaction):
        config = await self.store.get_guild(interaction.guild_id)
        status = "ativado" if config.get("enabled", True) else "desativado"
        await interaction.response.send_message(f"Sistema de sorteios: **{status}**.", ephemeral=True)

    async def sorteio_ativar(self, interaction: discord.Interaction, ativado: bool):
        await self.store.set_enabled(interaction.guild_id, ativado)
        await interaction.response.send_message("Sistema de sorteios **ativado**." if ativado else "Sistema de sorteios **desativado**.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Giveaways(bot))
