"""Backup e diagnóstico em interações privadas; restauração exige confirmação."""
import io
import discord
from ..services.maintenance import export_backup, diagnose, restore_backup, validate_backup


class MaintenanceView(discord.ui.View):
    def __init__(self, store, guild_id, owner_id):
        super().__init__(timeout=180)
        self.store, self.guild_id, self.owner_id = store, guild_id, owner_id

    async def interaction_check(self, interaction):
        from .permissions import admin_only
        return await admin_only(interaction, self.guild_id, self.owner_id)

    @discord.ui.button(label='Diagnóstico', emoji='🩺', style=discord.ButtonStyle.primary)
    async def diagnostic(self, interaction, button):
        try:
            data = await self.store.get(self.guild_id)
            findings = diagnose(data, interaction.guild)
        except (ValueError, OSError) as exc:
            return await interaction.response.send_message(f'❌ Falha ao ler JSON: {exc}', ephemeral=True)
        text = '\n'.join(f'**{level.upper()}** • {message}' for level, message in findings[:20])
        if len(findings) > 20:
            text += f'\n… e mais {len(findings)-20} ocorrências.'
        await interaction.response.send_message('**Diagnóstico local do Reaction Roles**\n'+text[:1900], ephemeral=True)

    @discord.ui.button(label='Baixar backup JSON', emoji='📦', style=discord.ButtonStyle.secondary)
    async def backup(self, interaction, button):
        try:
            content = await export_backup(self.store, self.guild_id)
        except (ValueError, OSError) as exc:
            return await interaction.response.send_message(f'❌ Falha ao exportar: {exc}', ephemeral=True)
        file = discord.File(io.BytesIO(content), filename=f'kingplus_rr_{self.guild_id}_backup.json')
        await interaction.response.send_message('Backup deste servidor. Guarde o arquivo em local seguro.', file=file, ephemeral=True)

    @discord.ui.button(label='Restaurar JSON', emoji='♻️', style=discord.ButtonStyle.secondary)
    async def restore(self, interaction, button):
        from ..services.maintenance import validate_backup, MAX_BACKUP_BYTES
        import asyncio
        if interaction.channel is None:
            return await interaction.response.send_message('Canal indisponível.', ephemeral=True)
        await interaction.response.send_message(
            'Envie o backup `.json` **neste canal** nos próximos 90 segundos. '
            '⚠️ O arquivo será uma mensagem comum, visível a quem acessa o canal. '
            'Use um canal administrativo privado. O bot tentará apagar o upload após ler.', ephemeral=True)
        def check(message):
            return (message.author.id == self.owner_id and message.guild is not None
                    and message.guild.id == self.guild_id
                    and message.channel.id == interaction.channel.id and bool(message.attachments))
        try:
            message = await interaction.client.wait_for('message', check=check, timeout=90)
        except asyncio.TimeoutError:
            return await interaction.followup.send('Tempo esgotado. Tente novamente.', ephemeral=True)
        try:
            attachment = message.attachments[0]
            if not attachment.filename.lower().endswith('.json') or attachment.size > MAX_BACKUP_BYTES:
                raise ValueError('Envie um arquivo JSON de até 2 MB.')
            raw = await attachment.read()
            data = validate_backup(raw, self.guild_id)
        except (ValueError, discord.HTTPException) as exc:
            return await interaction.followup.send(f'Backup recusado: {exc}', ephemeral=True)
        finally:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
        await interaction.followup.send(
            f'⚠️ Restaurar {len(data["panels"])} painéis? Isso substituirá as configurações atuais.',
            view=RestoreConfirmation(self.store, self.guild_id, self.owner_id, raw), ephemeral=True)


class RestoreConfirmation(discord.ui.View):
    def __init__(self, store, guild_id, owner_id, payload):
        super().__init__(timeout=120)
        self.store, self.guild_id, self.owner_id, self.payload = store, guild_id, owner_id, payload

    async def interaction_check(self, interaction):
        from .permissions import admin_only
        return await admin_only(interaction, self.guild_id, self.owner_id)

    @discord.ui.button(label='Confirmar restauração', emoji='⚠️', style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            # Make a recovery snapshot before replacement.
            previous = await export_backup(self.store, self.guild_id)
            count = await restore_backup(self.store, self.guild_id, self.payload)
            backup = discord.File(io.BytesIO(previous), filename=f'kingplus_rr_{self.guild_id}_antes_da_restauracao.json')
            await interaction.followup.send(
                f'✅ Restaurados {count} painéis. Backup anterior anexado. '
                'Reinicie o bot para registrar novamente os componentes persistentes. '
                'Publicações removidas do Discord não são recriadas automaticamente.',
                file=backup, ephemeral=True)
        except (ValueError, OSError) as exc:
            await interaction.followup.send(f'❌ Restauração não concluída: {exc}', ephemeral=True)
        self.stop()
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label='Cancelar', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self.stop()
        await interaction.response.edit_message(content='Restauração cancelada.', view=None)
