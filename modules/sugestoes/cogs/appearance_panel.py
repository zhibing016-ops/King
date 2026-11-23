import discord
from discord import app_commands
from discord.ext import commands
from modules.sugestoes.storage import read_data, mutate
from modules.sugestoes.appearance import DEFAULTS, color_hex, valid_url, theme, panel_embed


def allowed(interaction):
    return bool(interaction.guild and interaction.user.guild_permissions.manage_guild)


class TextModal(discord.ui.Modal, title="Editar textos do painel"):
    def __init__(self, current):
        super().__init__()
        self.title_input = discord.ui.TextInput(label="Título", default=current["panel_title"], max_length=256)
        self.description_input = discord.ui.TextInput(label="Descrição", default=current["panel_description"], style=discord.TextStyle.paragraph, max_length=4000)
        self.footer_input = discord.ui.TextInput(label="Rodapé (opcional)", default=current["panel_footer"], required=False, max_length=200)
        for field in (self.title_input, self.description_input, self.footer_input): self.add_item(field)

    async def on_submit(self, interaction):
        if not allowed(interaction): return await interaction.response.send_message("Sem permissão.", ephemeral=True)
        def save(d):
            t = d.setdefault("settings", {}).setdefault("appearance", {})
            t.update(panel_title=self.title_input.value, panel_description=self.description_input.value, panel_footer=self.footer_input.value)
        await mutate(interaction.guild_id, save)
        await interaction.response.send_message("Textos salvos. Publique novamente o painel para atualizar a mensagem pública.", ephemeral=True)


class ColorModal(discord.ui.Modal, title="Configurar cores"):
    panel = discord.ui.TextInput(label="Cor do painel (#RRGGBB)", default="#5865F2", max_length=7)
    suggestion = discord.ui.TextInput(label="Cor das sugestões (#RRGGBB)", default="#5865F2", max_length=7)
    async def on_submit(self, interaction):
        if not allowed(interaction): return await interaction.response.send_message("Sem permissão.", ephemeral=True)
        try: a, b = color_hex(self.panel.value), color_hex(self.suggestion.value)
        except ValueError as exc: return await interaction.response.send_message(str(exc), ephemeral=True)
        def save(d): d.setdefault("settings", {}).setdefault("appearance", {}).update(panel_color=a, suggestion_color=b)
        await mutate(interaction.guild_id, save)
        await interaction.response.send_message("Cores salvas. A cor das sugestões novas será aplicada automaticamente.", ephemeral=True)


class ImageModal(discord.ui.Modal, title="Imagens do painel"):
    image = discord.ui.TextInput(label="URL HTTPS da imagem (opcional)", required=False, max_length=500)
    thumbnail = discord.ui.TextInput(label="URL HTTPS do thumbnail (opcional)", required=False, max_length=500)
    async def on_submit(self, interaction):
        if not allowed(interaction): return await interaction.response.send_message("Sem permissão.", ephemeral=True)
        if not valid_url(self.image.value) or not valid_url(self.thumbnail.value):
            return await interaction.response.send_message("URL inválida. Informe uma URL HTTPS pública ou deixe em branco.", ephemeral=True)
        def save(d): d.setdefault("settings", {}).setdefault("appearance", {}).update(panel_image=self.image.value, panel_thumbnail=self.thumbnail.value)
        await mutate(interaction.guild_id, save)
        await interaction.response.send_message("URLs salvas. Publique novamente o painel para aplicar.", ephemeral=True)


class AppearanceView(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id or not allowed(interaction):
            await interaction.response.send_message("Este painel é privado do administrador que o abriu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Textos", emoji="📝", style=discord.ButtonStyle.primary)
    async def texts(self, interaction, button):
        await interaction.response.send_modal(TextModal(theme(await read_data(interaction.guild_id))))

    @discord.ui.button(label="Cores", emoji="🎨", style=discord.ButtonStyle.secondary)
    async def colors(self, interaction, button):
        await interaction.response.send_modal(ColorModal())

    @discord.ui.button(label="Imagens", emoji="🖼️", style=discord.ButtonStyle.secondary)
    async def images(self, interaction, button):
        await interaction.response.send_modal(ImageModal())

    @discord.ui.button(label="Pré-visualizar", emoji="👁️", style=discord.ButtonStyle.success, row=1)
    async def preview(self, interaction, button):
        from modules.sugestoes.cogs.suggestions import PainelSugestoes
        embed = panel_embed(theme(await read_data(interaction.guild_id)))
        await interaction.response.send_message("Prévia privada do painel (botões de exemplo):", embed=embed, ephemeral=True)

    @discord.ui.button(label="Restaurar padrão", emoji="↩️", style=discord.ButtonStyle.danger, row=1)
    async def reset(self, interaction, button):
        def save(d): d.setdefault("settings", {}).pop("appearance", None)
        await mutate(interaction.guild_id, save)
        await interaction.response.send_message("Aparência restaurada. Publique o painel novamente para aplicar.", ephemeral=True)


class AppearanceCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="sugestao_personalizar", description="Personaliza o painel e os embeds de sugestões")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def personalize(self, interaction: discord.Interaction):
        if not allowed(interaction): return await interaction.response.send_message("Sem permissão.", ephemeral=True)
        await interaction.response.send_message("**KING PLUS • Aparência**\nEscolha o que deseja configurar. Use Pré-visualizar antes de republicar o painel.", view=AppearanceView(interaction.user.id), ephemeral=True)


async def setup(bot): await bot.add_cog(AppearanceCog(bot))
