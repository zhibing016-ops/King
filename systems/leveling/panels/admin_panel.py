"""Painel efêmero de administração do sistema de níveis."""
import discord
from ..announcements import validate_template, render_announcement, DEFAULT_MESSAGE


def admin_only():
    return "❌ Você precisa da permissão Gerenciar Servidor."

class XPModal(discord.ui.Modal, title="KING PLUS • Configurar XP"):
    minimum = discord.ui.TextInput(label="XP mínimo (1-1000)", max_length=4)
    maximum = discord.ui.TextInput(label="XP máximo (1-1000)", max_length=4)
    cooldown = discord.ui.TextInput(label="Cooldown em segundos (5-3600)", max_length=4)
    def __init__(self, cog):
        super().__init__(); self.cog = cog
    async def on_submit(self, interaction):
        try:
            a,b,c = int(self.minimum.value),int(self.maximum.value),int(self.cooldown.value)
            if not (1 <= a <= b <= 1000 and 5 <= c <= 3600): raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Use XP mínimo ≤ máximo (1–1000) e cooldown de 5–3600s.", ephemeral=True); return
        await self.cog.storage.update_config(interaction.guild_id, xp_per_message_min=a, xp_per_message_max=b, cooldown_seconds=c)
        await interaction.response.send_message("✅ Configuração de XP atualizada.", ephemeral=True)

class MessageModal(discord.ui.Modal, title="KING PLUS • Mensagem de nível"):
    message = discord.ui.TextInput(label="Mensagem", style=discord.TextStyle.paragraph, max_length=1000)
    def __init__(self, cog, current):
        super().__init__(); self.cog=cog; self.message.default=current[:1000]
    async def on_submit(self, interaction):
        try: validate_template(self.message.value)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True); return
        await self.cog.storage.update_config(interaction.guild_id, level_up_message=self.message.value)
        await interaction.response.send_message("✅ Mensagem atualizada.", ephemeral=True)

class RewardModal(discord.ui.Modal, title="KING PLUS • Recompensa"):
    level = discord.ui.TextInput(label="Nível (1-10000)", max_length=5)
    role_id = discord.ui.TextInput(label="ID do cargo", max_length=22)
    def __init__(self, cog): super().__init__(); self.cog=cog
    async def on_submit(self, interaction):
        try:
            level=int(self.level.value); rid=int(self.role_id.value)
            if not 1<=level<=10000: raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Nível ou ID inválido.", ephemeral=True); return
        role=interaction.guild.get_role(rid)
        me=interaction.guild.me
        if role is None or role.is_default() or role.managed or me is None or role>=me.top_role:
            await interaction.response.send_message("❌ Cargo inexistente ou acima do bot.", ephemeral=True); return
        data=await self.cog.storage.get(interaction.guild_id)
        rewards=dict(data['config'].get('rewards',{})); rewards[str(level)]=rid
        await self.cog.storage.update_config(interaction.guild_id,rewards=rewards)
        await interaction.response.send_message(f"✅ Nível {level}: {role.mention}",ephemeral=True)

class ChannelSelect(discord.ui.ChannelSelect):
    def __init__(self,cog):
        super().__init__(placeholder="Canal de anúncios",channel_types=[discord.ChannelType.text],min_values=1,max_values=1)
        self.cog=cog
    async def callback(self,interaction):
        await self.cog.storage.update_config(interaction.guild_id,level_up_channel_id=self.values[0].id)
        await interaction.response.send_message("✅ Canal de anúncios atualizado.",ephemeral=True)

class ChannelView(discord.ui.View):
    def __init__(self,cog):
        super().__init__(timeout=180);self.add_item(ChannelSelect(cog))

class AdminPanel(discord.ui.View):
    def __init__(self,cog,owner_id):
        super().__init__(timeout=300);self.cog=cog;self.owner_id=owner_id
    async def interaction_check(self,interaction):
        if interaction.guild is None or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(admin_only(),ephemeral=True);return False
        if interaction.user.id!=self.owner_id:
            await interaction.response.send_message("Abra seu próprio painel com /nivel painel.",ephemeral=True);return False
        return True
    async def show(self,interaction):
        config=(await self.cog.storage.get(interaction.guild_id))['config']
        embed=discord.Embed(title="🏆 KING PLUS • Painel de Níveis",color=discord.Color.blurple())
        embed.add_field(name="Sistema",value="🟢 Ativo" if config['enabled'] else "🔴 Desativado")
        embed.add_field(name="XP por mensagem",value=f"{config['xp_per_message_min']}–{config['xp_per_message_max']}")
        embed.add_field(name="Cooldown",value=f"{config['cooldown_seconds']}s")
        embed.add_field(name="Avisos",value="Ativos" if config['announce_level_up'] else "Desativados")
        embed.add_field(name="Recompensas",value=str(len(config.get('rewards',{}))))
        embed.add_field(name="Canal",value=f"<#{config['level_up_channel_id']}>" if config.get('level_up_channel_id') else "Canal da mensagem")
        embed.set_footer(text="Fase 8 • Configurações salvas em JSON")
        return embed
    @discord.ui.button(label="Ativar / Desativar",style=discord.ButtonStyle.success,row=0)
    async def toggle(self,interaction,button):
        cfg=(await self.cog.storage.get(interaction.guild_id))['config']
        await self.cog.storage.update_config(interaction.guild_id,enabled=not cfg['enabled'])
        await interaction.response.edit_message(embed=await self.show(interaction),view=self)
    @discord.ui.button(label="Configurar XP",style=discord.ButtonStyle.primary,row=0)
    async def xp(self,interaction,button): await interaction.response.send_modal(XPModal(self.cog))
    @discord.ui.button(label="Recompensa",style=discord.ButtonStyle.secondary,row=0)
    async def reward(self,interaction,button): await interaction.response.send_modal(RewardModal(self.cog))
    @discord.ui.button(label="Avisos ON/OFF",style=discord.ButtonStyle.secondary,row=1)
    async def notices(self,interaction,button):
        cfg=(await self.cog.storage.get(interaction.guild_id))['config']
        await self.cog.storage.update_config(interaction.guild_id,announce_level_up=not cfg['announce_level_up'])
        await interaction.response.edit_message(embed=await self.show(interaction),view=self)
    @discord.ui.button(label="Editar mensagem",style=discord.ButtonStyle.secondary,row=1)
    async def message(self,interaction,button):
        cfg=(await self.cog.storage.get(interaction.guild_id))['config']
        await interaction.response.send_modal(MessageModal(self.cog,cfg.get('level_up_message',DEFAULT_MESSAGE)))
    @discord.ui.button(label="Canal de avisos",style=discord.ButtonStyle.secondary,row=1)
    async def channel(self,interaction,button):
        await interaction.response.send_message("Escolha o canal:",view=ChannelView(self.cog),ephemeral=True)
    @discord.ui.button(label="Prévia",style=discord.ButtonStyle.secondary,row=2)
    async def preview(self,interaction,button):
        cfg=(await self.cog.storage.get(interaction.guild_id))['config']
        content=render_announcement(cfg.get('level_up_message',DEFAULT_MESSAGE),member_name=interaction.user.display_name,member_id=interaction.user.id,level=10,previous_level=9,guild_name=interaction.guild.name)
        await interaction.response.send_message("🔎 **Prévia**\n"+content,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    @discord.ui.button(label="Atualizar painel",style=discord.ButtonStyle.primary,row=2)
    async def refresh(self,interaction,button):
        await interaction.response.edit_message(embed=await self.show(interaction),view=self)
