import re
import discord

DEFAULTS = {'title': '🎉 SORTEIO • {prize}', 'color': '#5865F2', 'image': '', 'thumbnail': '', 'footer': 'KING PLUS • Sorteios'}


def appearance_of(config):
    return {**DEFAULTS, **config.get('appearance', {})}


def build_embed(prize, description, winners, ends_at, appearance):
    title = appearance['title'].replace('{prize}', prize)
    embed = discord.Embed(title=title, description=description or 'Participe deste sorteio!', color=int(appearance['color'][1:], 16))
    embed.add_field(name='🏆 Vencedores', value=str(winners), inline=True)
    embed.add_field(name='⏰ Termina', value=f'<t:{int(ends_at.timestamp())}:R>', inline=True)
    embed.add_field(name='📌 Estado', value='Aberto • participação liberada', inline=False)
    if appearance['image']:
        embed.set_image(url=appearance['image'])
    if appearance['thumbnail']:
        embed.set_thumbnail(url=appearance['thumbnail'])
    if appearance['footer']:
        embed.set_footer(text=appearance['footer'])
    return embed


def validate_url(value):
    value = value.strip()
    if value and (not value.startswith('https://') or len(value) > 500 or any(c.isspace() for c in value)):
        raise ValueError('As imagens precisam de URL HTTPS válida (máximo 500 caracteres).')
    return value


class AppearanceModal(discord.ui.Modal, title='🎨 Aparência dos sorteios'):
    def __init__(self, cog, config):
        super().__init__()
        self.cog = cog
        current = appearance_of(config)
        self.title_input = discord.ui.TextInput(label='Título ({prize} = prêmio)', default=current['title'], max_length=180)
        self.color_input = discord.ui.TextInput(label='Cor hexadecimal', default=current['color'], max_length=7)
        self.image_input = discord.ui.TextInput(label='URL HTTPS da imagem (opcional)', default=current['image'], required=False, max_length=500)
        self.thumbnail_input = discord.ui.TextInput(label='URL HTTPS da miniatura (opcional)', default=current['thumbnail'], required=False, max_length=500)
        self.footer_input = discord.ui.TextInput(label='Rodapé (opcional)', default=current['footer'], required=False, max_length=200)
        for field in (self.title_input, self.color_input, self.image_input, self.thumbnail_input, self.footer_input):
            self.add_item(field)

    async def on_submit(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message('⛔ Gerenciar Servidor necessário.', ephemeral=True)
        try:
            color = str(self.color_input).strip().upper()
            if not re.fullmatch(r'#[0-9A-F]{6}', color):
                raise ValueError('A cor deve estar no formato #5865F2.')
            appearance = {'title': str(self.title_input).strip(), 'color': color,
                          'image': validate_url(str(self.image_input)),
                          'thumbnail': validate_url(str(self.thumbnail_input)),
                          'footer': str(self.footer_input).strip()}
            if not appearance['title']:
                raise ValueError('O título não pode ficar vazio.')
            await self.cog.store.set_appearance(interaction.guild_id, appearance)
        except ValueError as exc:
            return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
        await interaction.response.send_message('✅ Aparência salva! Os próximos sorteios usarão este visual.', ephemeral=True)


class AppearancePanel(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=600)
        self.cog = cog

    async def interaction_check(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message('⛔ Gerenciar Servidor necessário.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Editar aparência', emoji='🎨', style=discord.ButtonStyle.primary)
    async def edit(self, interaction, button):
        config = await self.cog.store.get_guild(interaction.guild_id)
        await interaction.response.send_modal(AppearanceModal(self.cog, config))

    @discord.ui.button(label='Pré-visualizar', emoji='👁️', style=discord.ButtonStyle.secondary)
    async def preview(self, interaction, button):
        from datetime import datetime, timedelta, timezone
        config = await self.cog.store.get_guild(interaction.guild_id)
        embed = build_embed('Discord Nitro', 'Exemplo de descrição do sorteio.', 2, datetime.now(timezone.utc) + timedelta(days=1), appearance_of(config))
        await interaction.response.send_message('👁️ Prévia da aparência atual:', embed=embed, ephemeral=True)

    @discord.ui.button(label='Restaurar padrão', emoji='↩️', style=discord.ButtonStyle.danger)
    async def reset(self, interaction, button):
        await self.cog.store.set_appearance(interaction.guild_id, dict(DEFAULTS))
        await interaction.response.send_message('✅ Aparência padrão restaurada.', ephemeral=True)
