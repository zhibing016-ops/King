"""Fase 05: fila administrativa paginada, filtros e ações de revisão."""
import discord
from discord import app_commands
from discord.ext import commands
from modules.sugestoes.storage import read_data
from .suggestions import STATUS_VALIDOS, CORES_STATUS, alterar_status
from modules.sugestoes.permissions import can_review

PAGE_SIZE = 5
FILTERS = {"Todas": None, "Pendentes": "Pendente", "Em análise": "Em análise", "Aprovadas": "Aprovada", "Rejeitadas": "Rejeitada"}


class FilterSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Filtrar sugestões por status", min_values=1, max_values=1,
                         options=[discord.SelectOption(label=k, value=k) for k in FILTERS])

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.filter_name = self.values[0]
        view.page = 0
        await view.refresh(interaction)


class QueueView(discord.ui.View):
    """Sessão efêmera por administrador; não requer persistência após reinício."""
    def __init__(self, guild_id: int, owner_id: int):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.filter_name = "Todas"
        self.page = 0
        self.add_item(FilterSelect())

    async def interaction_check(self, interaction):
        if interaction.guild_id != self.guild_id or interaction.user.id != self.owner_id or not await can_review(interaction):
            await interaction.response.send_message("Esta fila pertence a outro administrador ou você não tem permissão.", ephemeral=True)
            return False
        return True

    async def snapshot(self):
        data = await read_data(self.guild_id)
        items = [(int(k), v) for k, v in data.get("suggestions", {}).items()
                 if k.isdigit() and v.get("status") != "Falha no envio"
                 and (FILTERS[self.filter_name] is None or v.get("status", "Pendente") == FILTERS[self.filter_name])]
        items.sort(key=lambda item: item[0], reverse=True)
        return items

    async def render(self):
        items = await self.snapshot()
        pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page = max(0, min(self.page, pages - 1))
        subset = items[self.page * PAGE_SIZE:(self.page + 1) * PAGE_SIZE]
        embed = discord.Embed(title="📋 KING PLUS • Fila de sugestões",
                              description=f"Filtro: **{self.filter_name}** | Página **{self.page + 1}/{pages}** | Total: **{len(items)}**",
                              color=discord.Color.blurple())
        if not subset:
            embed.add_field(name="Nenhuma sugestão", value="Não existem sugestões para este filtro.", inline=False)
        for number, entry in subset:
            text = entry.get("text", "(sem descrição)").replace("\n", " ")
            status = entry.get("status", "Pendente")
            embed.add_field(name=f"#{number} • {status}", value=f"{text[:170]}{'…' if len(text) > 170 else ''}\nAutor: {'Anônimo' if entry.get('anonymous') else '<@' + str(entry.get('author_id', 0)) + '>'}", inline=False)
        self.previous.disabled = self.page == 0
        self.next_page.disabled = self.page >= pages - 1
        return embed

    async def refresh(self, interaction):
        embed = await self.render()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Anterior", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def previous(self, interaction, button):
        self.page -= 1
        await self.refresh(interaction)

    @discord.ui.button(label="Próxima", emoji="➡️", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction, button):
        self.page += 1
        await self.refresh(interaction)

    @discord.ui.button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.primary, row=1)
    async def reload(self, interaction, button):
        await self.refresh(interaction)

    @discord.ui.button(label="Gerenciar por ID", emoji="🛡️", style=discord.ButtonStyle.success, row=1)
    async def manage(self, interaction, button):
        await interaction.response.send_modal(QueueActionModal(self))


class QueueActionModal(discord.ui.Modal, title="Revisar sugestão da fila"):
    suggestion_id = discord.ui.TextInput(label="ID da sugestão", placeholder="Ex.: 15", max_length=12)
    status = discord.ui.TextInput(label="Novo status", placeholder="Pendente / Em análise / Aprovada / Rejeitada", max_length=20)

    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    async def on_submit(self, interaction):
        if interaction.user.id != self.queue.owner_id or not await can_review(interaction):
            return await interaction.response.send_message("Sem permissão.", ephemeral=True)
        try:
            number = int(self.suggestion_id.value)
            if number <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("ID inválido.", ephemeral=True)
        status = next((s for s in STATUS_VALIDOS if s.casefold() == self.status.value.strip().casefold()), None)
        if status is None:
            return await interaction.response.send_message("Status inválido. Use Pendente, Em análise, Aprovada ou Rejeitada.", ephemeral=True)
        await alterar_status(interaction, number, status)
        # A fila pode ser atualizada pelo botão Atualizar.


class SuggestionQueue(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="sugestao_fila", description="Abre a fila administrativa de sugestões")
    @app_commands.guild_only()
    async def sugestao_fila(self, interaction: discord.Interaction):
        if not await can_review(interaction):
            return await interaction.response.send_message("Acesso reservado à equipe de sugestões.", ephemeral=True)
        view = QueueView(interaction.guild_id, interaction.user.id)
        embed = await view.render()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(SuggestionQueue(bot))
