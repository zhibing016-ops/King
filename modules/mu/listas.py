import discord
from discord.ui import View, Button, Modal, TextInput, Select
from discord.ext import commands
from .config import load_config, save_config

import asyncio


# ======================================================
# CONFIG + NORMALIZAÇÃO
# ======================================================
def get_cfg():
    cfg = load_config()
    cfg.setdefault("listas", {})
    cfg.setdefault("painel_listas", {"canal_id": None, "mensagem_id": None, "lista_ativa": None})
    for nome, itens in list(cfg["listas"].items()):
        if isinstance(itens, list):
            cfg["listas"][nome] = {str(j): {} for j in itens}
        elif isinstance(itens, dict):
            cfg["listas"][nome] = {str(j): {} for j in itens}
        else:
            cfg["listas"][nome] = {}
    return cfg


def montar_tabela(itens: dict) -> str:
    linhas = [f"{i}. {nome}" for i, nome in enumerate(itens, 1)]
    return "\n".join(linhas) if linhas else "— vazia —"


# ======================================================
# ATUALIZAÇÃO DO PAINEL (SEM RECRIAR)
# ======================================================
async def atualizar_painel_fixo(bot):
    cfg = get_cfg()
    painel = cfg["painel_listas"]

    if not painel["canal_id"] or not painel["mensagem_id"]:
        return

    canal = bot.get_channel(painel["canal_id"])
    if not canal:
        return

    try:
        msg = await canal.fetch_message(painel["mensagem_id"])
    except:
        return

    embed = discord.Embed(
        title="📋 Leilão Guild",
        color=discord.Color.dark_grey()
    )

    for nome_lista, itens in cfg["listas"].items():
        embed.add_field(
            name=f"🔥 {nome_lista}",
            value=montar_tabela(itens)[:1024] if itens else "— vazia —",
            inline=False
        )

    await msg.edit(embed=embed, view=ListaPainel())


# ======================================================
# SELECT LISTA
# ======================================================
class SelectLista(Select):
    def __init__(self):
        cfg = get_cfg()
        options = [
            discord.SelectOption(label=nome)
            for nome in cfg["listas"].keys()
        ]

        super().__init__(
            placeholder="📂 Selecionar lista",
            options=options,
            custom_id="listas:select"
        )

    async def callback(self, interaction: discord.Interaction):
        cfg = get_cfg()
        lista = self.values[0]

        if lista not in cfg["listas"]:
            await interaction.response.send_message(
                "❌ Esta lista não existe mais.",
                ephemeral=True
            )
            return

        cfg["painel_listas"]["lista_ativa"] = lista
        save_config(cfg)

        await interaction.response.defer(ephemeral=True)
        await atualizar_painel_fixo(interaction.client)
        await interaction.followup.send(
            f"📂 Lista ativa: **{lista}**",
            ephemeral=True
        )


# ======================================================
# VIEW PRINCIPAL (PERSISTENTE)
# ======================================================
class ListaPainel(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.atualizar_itens()

    def atualizar_itens(self):
        self.clear_items()
        cfg = get_cfg()

        # Select SEMPRE atualizado
        if cfg["listas"]:
            self.add_item(SelectLista())

        self.add_item(BtnCriarLista())
        self.add_item(BtnExcluirLista())
        self.add_item(BtnAdd())
        self.add_item(BtnRemove())
        self.add_item(BtnPassar())
        self.add_item(BtnConcluir())


# ======================================================
# BOTÕES
# ======================================================
class BtnCriarLista(Button):
    def __init__(self):
        super().__init__(
            label="Criar Lista",
            emoji="➕",
            style=discord.ButtonStyle.success,
            custom_id="btn_criar"
        )

    async def callback(self, interaction):
        await interaction.response.send_modal(ModalCriarLista())

class ModalCriarLista(Modal, title="Criar lista"):
    nome = TextInput(label="Nome da lista", max_length=90, required=True)

    async def on_submit(self, interaction):
        nome = self.nome.value.strip()
        cfg = get_cfg()
        if not nome:
            return await interaction.response.send_message("Nome inválido.", ephemeral=True)
        if nome in cfg["listas"]:
            return await interaction.response.send_message("Esta lista já existe.", ephemeral=True)
        if len(cfg["listas"]) >= 25:
            return await interaction.response.send_message("Limite de 25 listas atingido.", ephemeral=True)
        cfg["listas"][nome] = {}
        cfg["painel_listas"]["lista_ativa"] = nome
        save_config(cfg)
        await interaction.response.send_message("Lista criada!", ephemeral=True)
        await atualizar_painel_fixo(interaction.client)


class BtnExcluirLista(Button):
    def __init__(self):
        super().__init__(
            label="Excluir Lista",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            custom_id="btn_excluir"
        )

    async def callback(self, interaction):
        if not get_cfg()["listas"]:
            return await interaction.response.send_message("Não há listas para excluir.", ephemeral=True)
        await interaction.response.send_message(
            "Selecione a lista para excluir:",
            view=ViewExcluirLista(),
            ephemeral=True
        )


class BtnAdd(Button):
    def __init__(self):
        super().__init__(
            label="Adicionar",
            emoji="➕",
            style=discord.ButtonStyle.success,
            custom_id="btn_add"
        )

    async def callback(self, interaction):
        cfg = get_cfg()
        lista = cfg["painel_listas"]["lista_ativa"]
        if not lista:
            return await interaction.response.send_message(
                "⚠️ Nenhuma lista ativa.",
                ephemeral=True
            )
        await interaction.response.send_modal(ModalAdd(lista))


class BtnRemove(Button):
    def __init__(self):
        super().__init__(
            label="Remover",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            custom_id="listas:remove"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("Digite o número:", ephemeral=True)
        await tratar_indice(interaction, "remove")


class BtnPassar(Button):
    def __init__(self):
        super().__init__(
            label="PASSAR",
            emoji="⏭️",
            style=discord.ButtonStyle.secondary,
            custom_id="listas:passar"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("Digite o número:", ephemeral=True)
        await tratar_indice(interaction, "passar")


class BtnConcluir(Button):
    def __init__(self):
        super().__init__(
            label="Concluir Nº",
            emoji="🔁",
            style=discord.ButtonStyle.primary,
            custom_id="listas:concluir"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("Digite o número:", ephemeral=True)
        await tratar_indice(interaction, "concluir")


# ======================================================
# AÇÕES NUMÉRICAS
# ======================================================
async def tratar_indice(interaction, acao):
    def check(m):
        return (
            m.author == interaction.user
            and m.channel == interaction.channel
            and m.content.isdigit()
        )

    try:
        msg = await interaction.client.wait_for("message", timeout=30, check=check)
        idx = int(msg.content) - 1

        cfg = get_cfg()
        lista = cfg["painel_listas"]["lista_ativa"]

        if not lista or lista not in cfg["listas"]:
            await interaction.followup.send("❌ Lista inválida.", ephemeral=True)
            return

        itens = list(cfg["listas"][lista].items())
        if idx < 0 or idx >= len(itens):
            await interaction.followup.send("❌ Número inválido.", ephemeral=True)
            return

        nome, data = itens[idx]
        cfg["listas"][lista].pop(nome)
        if acao in ("concluir", "passar"):
            cfg["listas"][lista][nome] = {}

        save_config(cfg)
        await msg.delete()
        await atualizar_painel_fixo(interaction.client)
        await interaction.followup.send("✅ Ação realizada.", ephemeral=True)

    except asyncio.TimeoutError:
        await interaction.followup.send("⏱️ Tempo esgotado.", ephemeral=True)


# ======================================================
# MODAL ADD
# ======================================================
class ModalAdd(Modal, title="Adicionar itens"):
    nome1 = TextInput(label="Nome 1", required=True)
    nome2 = TextInput(label="Nome 2", required=False)
    nome3 = TextInput(label="Nome 3", required=False)
    nome4 = TextInput(label="Nome 4", required=False)
    nome5 = TextInput(label="Nome 5", required=False)

    def __init__(self, lista):
        super().__init__()
        self.lista = lista

    async def on_submit(self, interaction):
        cfg = get_cfg()
        lista = cfg["listas"].setdefault(self.lista, {})

        for nome in [
            self.nome1.value, self.nome2.value, self.nome3.value,
            self.nome4.value, self.nome5.value
        ]:
            if nome:
                lista.setdefault(
                    nome.strip(),
                    {}
                )

        save_config(cfg)
        await atualizar_painel_fixo(interaction.client)
        await interaction.response.send_message("✅ Itens adicionados!", ephemeral=True)


# ======================================================
# EXCLUIR LISTA
# ======================================================
class SelectExcluirLista(Select):
    def __init__(self):
        cfg = get_cfg()
        super().__init__(
            placeholder="Selecione",
            options=[discord.SelectOption(label=l) for l in cfg["listas"]],
            custom_id="select_excluir"
        )

    async def callback(self, interaction):
        cfg = get_cfg()
        lista = self.values[0]

        cfg["listas"].pop(lista, None)
        cfg["painel_listas"]["lista_ativa"] = None
        save_config(cfg)

        await atualizar_painel_fixo(interaction.client)
        await interaction.response.send_message("🗑️ Lista excluída.", ephemeral=True)


class ViewExcluirLista(View):
    def __init__(self):
        super().__init__(timeout=None)
        if get_cfg()["listas"]:
            self.add_item(SelectExcluirLista())


# ======================================================
# COG
# ======================================================
class ListasAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ==================================================
    # AUTO-RECOVERY DO PAINEL AO INICIAR O BOT
    # ==================================================
    @commands.Cog.listener()
    async def on_ready(self):
        await asyncio.sleep(2)  # garante cache do Discord

        cfg = get_cfg()
        painel = cfg["painel_listas"]

        # Nada configurado ainda
        if not painel["canal_id"]:
            return

        canal = self.bot.get_channel(painel["canal_id"])
        if not canal:
            return

        # Se tinha mensagem salva, tenta recuperar
        if painel["mensagem_id"]:
            try:
                await canal.fetch_message(painel["mensagem_id"])
                # Mensagem existe → só atualiza
                await atualizar_painel_fixo(self.bot)
                return
            except discord.NotFound:
                # Mensagem não existe → reset para recriar
                painel["mensagem_id"] = None
                painel["lista_ativa"] = None
                save_config(cfg)

        # Recria painel automaticamente
        msg = await canal.send(
            embed=discord.Embed(
                title="📋 Leilão Guild",
                description="Inicializando...",
                color=discord.Color.dark_grey()
            ),
            view=ListaPainel()
        )

        try:
            await msg.pin()
        except discord.Forbidden:
            pass

        painel["mensagem_id"] = msg.id
        save_config(cfg)

        await atualizar_painel_fixo(self.bot)



async def setup(bot):
    await bot.add_cog(ListasAdmin(bot))

    bot.add_view(ListaPainel())  # 🔴 SEM ISSO OS BOTÕES MORREM
