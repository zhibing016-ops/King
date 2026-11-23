import asyncio
import discord


class ParticipationView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label='Participar / Sair', emoji='🎉', style=discord.ButtonStyle.success, custom_id='kingplus:giveaway:toggle')
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild_id or not interaction.message:
            return await interaction.response.send_message('Sorteio inválido.', ephemeral=True)
        if interaction.user.bot:
            return await interaction.response.send_message('Bots não podem participar.', ephemeral=True)
        record = await self.cog.store.get_giveaway(interaction.guild_id, interaction.message.id)
        if not record:
            return await interaction.response.send_message('❌ Sorteio não encontrado.', ephemeral=True)
        # Requisitos são verificados ao entrar, não ao sair.
        if interaction.user.id not in record.get('participants', []):
            error = self.cog.eligibility_error(interaction.user, record.get('requirements', {}))
            if error:
                return await interaction.response.send_message(f'❌ {error}', ephemeral=True)
        try:
            joined, count = await self.cog.store.toggle_participant(interaction.guild_id, interaction.message.id, interaction.user.id)
        except ValueError as exc:
            return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
        await interaction.response.send_message('✅ Participação confirmada!' if joined else '↩️ Você saiu do sorteio.', ephemeral=True)
        # O contador é atualizado a partir do JSON, não do valor capturado anteriormente.
        async with self.cog.message_update_lock(interaction.message.id):
            try:
                current = await interaction.channel.fetch_message(interaction.message.id)
                if not current.embeds:
                    return
                embed = current.embeds[0].copy()
                latest = await self.cog.store.participant_count(interaction.guild_id, interaction.message.id)
                idx = next((i for i, f in enumerate(embed.fields) if f.name == 'Participantes'), None)
                if idx is None:
                    embed.add_field(name='Participantes', value=str(latest), inline=True)
                else:
                    embed.set_field_at(idx, name='Participantes', value=str(latest), inline=True)
                await current.edit(embed=embed)
            except (discord.HTTPException, AttributeError):
                pass
