"""Permissões administrativas compartilhadas das views."""
import discord

async def admin_only(interaction, guild_id, owner_id):
    member = interaction.user
    allowed = (interaction.guild_id == guild_id and member.id == owner_id
               and isinstance(member, discord.Member) and member.guild_permissions.manage_guild)
    if not allowed:
        await interaction.response.send_message('❌ Somente o administrador que abriu o painel pode usá-lo.', ephemeral=True)
    return allowed

