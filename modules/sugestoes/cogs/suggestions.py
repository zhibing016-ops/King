import discord
from discord import app_commands
from discord.ext import commands
from modules.sugestoes.storage import read_data, mutate
from modules.sugestoes.permissions import can_review, is_manager
from modules.sugestoes.notifications import enviar_aviso_status
from modules.sugestoes.audit import record_event, send_audit_log
from modules.sugestoes.antispam import reserve_submission
from modules.sugestoes.appearance import theme, panel_embed

STATUS_VALIDOS = ("Pendente", "Em análise", "Aprovada", "Rejeitada")
CORES_STATUS = {"Pendente": discord.Color.blurple(), "Em análise": discord.Color.gold(), "Aprovada": discord.Color.green(), "Rejeitada": discord.Color.red()}

def pode_gerenciar(interaction):
    return bool(interaction.guild and interaction.user.guild_permissions.manage_guild)



async def publicar_sugestao(interaction: discord.Interaction, texto: str, anonimo: bool = False, imagem_url: str | None = None):
    if not interaction.guild:
        return await interaction.response.send_message("Use em um servidor.", ephemeral=True)

    data = await read_data(interaction.guild_id)
    settings = data.get("settings", {})
    if settings.get("maintenance_enabled", False):
        return await interaction.response.send_message("O sistema de sugestões está temporariamente em manutenção.", ephemeral=True)
    if anonimo and not settings.get("anonymous_enabled", False):
        return await interaction.response.send_message("Sugestões anônimas estão desativadas.", ephemeral=True)
    if imagem_url:
        from modules.sugestoes.discussion import valid_image_url
        if not settings.get("images_enabled", True) or not valid_image_url(imagem_url):
            return await interaction.response.send_message("Imagem desativada ou URL inválida. Use HTTPS e link direto para PNG, JPG, GIF ou WEBP.", ephemeral=True)
    channel_id = settings.get("channel_id")
    if not channel_id:
        return await interaction.response.send_message(
            "Canal não configurado. Um administrador deve usar /sugestao_canal.",
            ephemeral=True,
        )

    channel = interaction.guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return await interaction.response.send_message("Canal de sugestões inválido.", ephemeral=True)

    await interaction.response.defer(ephemeral=True, thinking=True)

    numero, erro = await reserve_submission(interaction.guild_id, interaction.user.id, texto, anonimo, imagem_url)
    if erro:
        return await interaction.followup.send(erro, ephemeral=True)

    def registrar_criacao(dados):
        record_event(dados, "suggestion_created", interaction.user.id, numero,
                     {"anonymous": anonimo})
    await mutate(interaction.guild_id, registrar_criacao)
    registro = (await read_data(interaction.guild_id))["suggestions"][str(numero)]
    view = VotacaoView(interaction.guild_id, numero)
    embed = montar_embed(numero, registro, theme(await read_data(interaction.guild_id)))

    try:
        mensagem = await channel.send(embed=embed, view=view)
    except (discord.Forbidden, discord.HTTPException):
        def marcar_falha(dados):
            dados["suggestions"][str(numero)]["status"] = "Falha no envio"
        await mutate(interaction.guild_id, marcar_falha)
        return await interaction.followup.send(
            "Não foi possível publicar. Verifique as permissões do bot.", ephemeral=True
        )

    def salvar_mensagem(dados):
        dados["suggestions"][str(numero)]["message_id"] = mensagem.id
        dados["suggestions"][str(numero)]["channel_id"] = channel.id

    await mutate(interaction.guild_id, salvar_mensagem)
    from modules.sugestoes.discussion import create_discussion_thread
    await create_discussion_thread(interaction.client, interaction.guild_id, numero, mensagem)
    interaction.client.add_view(view, message_id=mensagem.id)
    await send_audit_log(interaction.client, interaction.guild_id, "suggestion_created",
                         interaction.user.id, numero, {"anonymous": anonimo})
    await interaction.followup.send(
        f"Sugestão #{numero} enviada em {channel.mention}.", ephemeral=True
    )


def montar_embed(numero: int, registro: dict, visual: dict | None = None) -> discord.Embed:
    visual = visual or {}
    votos = registro.get("votes", {})
    positivos = sum(v == "up" for v in votos.values())
    negativos = sum(v == "down" for v in votos.values())
    embed = discord.Embed(
        title=f"💡 Sugestão #{numero}",
        description=registro["text"],
        color=int(visual["suggestion_color"], 16) if visual.get("suggestion_color") else CORES_STATUS.get(registro.get("status"), discord.Color.blurple()),
    )
    embed.add_field(name="Status", value=registro.get("status", "Pendente"), inline=False)
    embed.add_field(name="👍 Positivos", value=str(positivos), inline=True)
    embed.add_field(name="👎 Negativos", value=str(negativos), inline=True)
    if registro.get("image_url"):
        embed.set_image(url=registro["image_url"])
    if registro.get("thread_id"):
        embed.add_field(name="Discussão", value=f"<#{registro['thread_id']}>", inline=False)
    embed.set_footer(text="Autor: Anônimo" if registro.get("anonymous") else f"Autor ID: {registro['author_id']}")
    if visual.get("suggestion_footer"):
        embed.set_footer(text=("Autor: Anônimo" if registro.get("anonymous") else f"Autor ID: {registro['author_id']}") + " • " + visual["suggestion_footer"])
    if registro.get("reviewed_by"):
        embed.add_field(name="Última revisão", value=f"<@{registro['reviewed_by']}>", inline=False)
    return embed


class VotacaoView(discord.ui.View):
    def __init__(self, guild_id: int, numero: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.numero = numero

    async def processar(self, interaction: discord.Interaction, escolha: str):
        if interaction.guild_id != self.guild_id:
            return await interaction.response.send_message("Servidor inválido.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        def registrar(dados):
            registro = dados["suggestions"].get(str(self.numero))
            if not registro:
                return None
            votos = registro.setdefault("votes", {})
            usuario = str(interaction.user.id)
            anterior = votos.get(usuario)
            if anterior == escolha:
                del votos[usuario]
                acao = "removido"
            else:
                votos[usuario] = escolha
                acao = "alterado" if anterior else "registrado"
            return dict(registro), acao
        resultado = await mutate(self.guild_id, registrar)
        if resultado is None:
            return await interaction.followup.send("Sugestão não encontrada.", ephemeral=True)
        registro, acao = resultado
        # Releitura para mostrar contagem atual, mesmo em votações simultâneas.
        atual = (await read_data(self.guild_id))["suggestions"].get(str(self.numero))
        if atual:
            try:
                await interaction.message.edit(embed=montar_embed(self.numero, atual, theme(await read_data(self.guild_id))), view=self)
            except (discord.Forbidden, discord.HTTPException, AttributeError):
                return await interaction.followup.send(
                    f"Voto {acao} e salvo, mas não consegui atualizar a mensagem.", ephemeral=True
                )
        await interaction.followup.send(f"Seu voto foi {acao} com sucesso.", ephemeral=True)

    @discord.ui.button(label="Votar positivo", emoji="👍", style=discord.ButtonStyle.success,
                       custom_id="kingplus:sugestoes:up:v3")
    async def positivo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar(interaction, "up")

    @discord.ui.button(label="Votar negativo", emoji="👎", style=discord.ButtonStyle.danger,
                       custom_id="kingplus:sugestoes:down:v3")
    async def negativo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar(interaction, "down")


    @discord.ui.button(label="Comentar", emoji="💬", style=discord.ButtonStyle.secondary,
                       custom_id="kingplus:sugestoes:comment:v10")
    async def comentar(self, interaction: discord.Interaction, button: discord.ui.Button):
        from modules.sugestoes.discussion import CommentModal
        await interaction.response.send_modal(CommentModal(self.guild_id, self.numero))


async def alterar_status(interaction: discord.Interaction, numero: int, novo_status: str):
    if not await can_review(interaction):
        return await interaction.response.send_message("Sem permissão para revisar sugestões.", ephemeral=True)
    if novo_status not in STATUS_VALIDOS:
        return await interaction.response.send_message("Status inválido.", ephemeral=True)
    await interaction.response.defer(ephemeral=True, thinking=True)
    def atualizar(dados):
        registro = dados["suggestions"].get(str(numero))
        if not registro or registro.get("status") == "Falha no envio":
            return None
        anterior = registro.get("status", "Pendente")
        registro["status"] = novo_status
        registro["previous_status"] = anterior
        registro["reviewed_by"] = interaction.user.id
        record_event(dados, "status_changed", interaction.user.id, numero,
                     {"before": anterior, "after": novo_status})
        return dict(registro)
    registro = await mutate(interaction.guild_id, atualizar)
    if registro is None:
        return await interaction.followup.send("Sugestão não encontrada ou não publicada.", ephemeral=True)
    canal = interaction.guild.get_channel(registro.get("channel_id", 0))
    if canal is None:
        try:
            canal = await interaction.guild.fetch_channel(registro["channel_id"])
        except (discord.HTTPException, KeyError):
            canal = None
    await send_audit_log(interaction.client, interaction.guild_id, "status_changed",
                         interaction.user.id, numero, {"before": registro.get("previous_status"), "after": novo_status})
    aviso = await enviar_aviso_status(interaction.client, interaction.guild_id, numero, registro)
    try:
        if canal and registro.get("message_id"):
            mensagem = await canal.fetch_message(registro["message_id"])
            await mensagem.edit(embed=montar_embed(numero, registro, theme(await read_data(interaction.guild_id))), view=VotacaoView(interaction.guild_id, numero))
        else:
            raise ValueError("Mensagem não encontrada")
    except (discord.HTTPException, ValueError):
        return await interaction.followup.send(
            f"Status da sugestão #{numero} salvo como **{novo_status}** no JSON, mas não foi possível atualizar a mensagem.", ephemeral=True
        )
    await interaction.followup.send(f"Sugestão #{numero}: **{novo_status}**. {aviso}", ephemeral=True)


class NumeroSugestaoModal(discord.ui.Modal, title="Gerenciar sugestão"):
    numero = discord.ui.TextInput(label="ID da sugestão", placeholder="Exemplo: 15", max_length=12)

    def __init__(self, status: str):
        super().__init__()
        self.status = status

    async def on_submit(self, interaction: discord.Interaction):
        try:
            numero = int(self.numero.value)
            if numero <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("Informe um ID numérico positivo.", ephemeral=True)
        await alterar_status(interaction, numero, self.status)


class PainelAdministrativo(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def abrir(self, interaction, status):
        if not await can_review(interaction):
            return await interaction.response.send_message("Você não pertence à equipe de sugestões.", ephemeral=True)
        await interaction.response.send_modal(NumeroSugestaoModal(status))

    @discord.ui.button(label="Em análise", emoji="🔎", style=discord.ButtonStyle.secondary, custom_id="kingplus:sugestoes:admin:analise:v4")
    async def analise(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.abrir(interaction, "Em análise")

    @discord.ui.button(label="Aprovar", emoji="✅", style=discord.ButtonStyle.success, custom_id="kingplus:sugestoes:admin:aprovar:v4")
    async def aprovar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.abrir(interaction, "Aprovada")

    @discord.ui.button(label="Rejeitar", emoji="❌", style=discord.ButtonStyle.danger, custom_id="kingplus:sugestoes:admin:rejeitar:v4")
    async def rejeitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.abrir(interaction, "Rejeitada")

    @discord.ui.button(label="Reabrir", emoji="↩️", style=discord.ButtonStyle.primary, custom_id="kingplus:sugestoes:admin:reabrir:v4")
    async def reabrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.abrir(interaction, "Pendente")


class SugestaoModal(discord.ui.Modal, title="Enviar sugestão"):
    def __init__(self, anonimo: bool = False):
        super().__init__()
        self.anonimo = anonimo

    assunto = discord.ui.TextInput(
        label="Assunto",
        placeholder="Resumo da sua ideia",
        min_length=3,
        max_length=100,
    )
    detalhes = discord.ui.TextInput(
        label="Descreva sua sugestão",
        placeholder="Explique sua proposta para o servidor...",
        style=discord.TextStyle.paragraph,
        min_length=5,
        max_length=1400,
    )

    imagem = discord.ui.TextInput(label="URL da imagem (opcional)", required=False, max_length=500, placeholder="https://site.com/imagem.png")

    async def on_submit(self, interaction: discord.Interaction):
        texto = f"**{self.assunto.value}**\n\n{self.detalhes.value}"
        await publicar_sugestao(interaction, texto, self.anonimo, self.imagem.value.strip() or None)


class PainelSugestoes(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Enviar sugestão",
        emoji="💡",
        style=discord.ButtonStyle.primary,
        custom_id="kingplus:sugestoes:enviar:v2",
    )
    async def enviar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SugestaoModal())

    @discord.ui.button(label="Enviar anonimamente", emoji="🕶️", style=discord.ButtonStyle.secondary,
                       custom_id="kingplus:sugestoes:anonimo:v6")
    async def anonimo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        dados = await read_data(interaction.guild_id)
        if not dados.get("settings", {}).get("anonymous_enabled", False):
            return await interaction.response.send_message("Sugestões anônimas estão desativadas.", ephemeral=True)
        await interaction.response.send_modal(SugestaoModal(anonimo=True))


class Suggestions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="sugestao", description="Envie uma sugestão ao servidor")
    @app_commands.describe(texto="Descreva sua sugestão")
    @app_commands.guild_only()
    async def sugestao(self, interaction: discord.Interaction, texto: app_commands.Range[str, 5, 1500], imagem_url: str | None = None):
        await publicar_sugestao(interaction, texto, imagem_url=imagem_url)

    @app_commands.command(name="sugestao_anonima", description="Envie uma sugestão anônima")
    @app_commands.guild_only()
    async def sugestao_anonima(self, interaction: discord.Interaction, texto: app_commands.Range[str, 5, 1500], imagem_url: str | None = None):
        await publicar_sugestao(interaction, texto, anonimo=True, imagem_url=imagem_url)

    @app_commands.command(name="sugestao_anonimato", description="Ativa ou desativa sugestões anônimas")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def sugestao_anonimato(self, interaction: discord.Interaction, ativar: bool):
        def atualizar(dados):
            dados.setdefault("settings", {})["anonymous_enabled"] = ativar
        await mutate(interaction.guild_id, atualizar)
        await interaction.response.send_message(
            "Sugestões anônimas " + ("ativadas." if ativar else "desativadas."), ephemeral=True
        )

    @app_commands.command(name="sugestao_canal", description="Define o canal que recebe sugestões")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def sugestao_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        def mudar(dados):
            dados["settings"]["channel_id"] = canal.id
        await mutate(interaction.guild_id, mudar)
        await interaction.response.send_message(
            f"Canal de sugestões configurado: {canal.mention}", ephemeral=True
        )

    @app_commands.command(name="sugestao_admin", description="Publica o painel administrativo de sugestões")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def sugestao_admin(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = discord.Embed(
            title="🛡️ KING PLUS • Administração de Sugestões",
            description="Escolha uma ação e informe o ID. Somente a equipe autorizada pode alterar status.",
            color=discord.Color.dark_blue(),
        )
        try:
            mensagem = await canal.send(embed=embed, view=PainelAdministrativo())
        except (discord.Forbidden, discord.HTTPException):
            return await interaction.followup.send("Não foi possível enviar o painel. Confira minhas permissões.", ephemeral=True)
        def salvar(dados):
            dados["settings"]["admin_panel_channel_id"] = canal.id
            dados["settings"]["admin_panel_message_id"] = mensagem.id
        await mutate(interaction.guild_id, salvar)
        await interaction.followup.send(f"Painel administrativo publicado em {canal.mention}. Restrinja o acesso ao canal.", ephemeral=True)

    @app_commands.command(name="sugestao_status", description="Altera o status de uma sugestão pelo ID")
    @app_commands.guild_only()
    @app_commands.choices(status=[
        app_commands.Choice(name="Pendente", value="Pendente"),
        app_commands.Choice(name="Em análise", value="Em análise"),
        app_commands.Choice(name="Aprovada", value="Aprovada"),
        app_commands.Choice(name="Rejeitada", value="Rejeitada"),
    ])
    async def sugestao_status(self, interaction: discord.Interaction, numero: int, status: app_commands.Choice[str]):
        if numero <= 0:
            return await interaction.response.send_message("Informe um ID positivo.", ephemeral=True)
        await alterar_status(interaction, numero, status.value)

    @app_commands.command(name="sugestao_painel", description="Publica o painel de sugestões com botão")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def sugestao_painel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = panel_embed(theme(await read_data(interaction.guild_id)))
        try:
            msg = await canal.send(embed=embed, view=PainelSugestoes())
        except (discord.Forbidden, discord.HTTPException):
            return await interaction.followup.send(
                "Não consegui publicar o painel. Confira minhas permissões.", ephemeral=True
            )
        def salvar(dados):
            dados["settings"]["panel_channel_id"] = canal.id
            dados["settings"]["panel_message_id"] = msg.id
        await mutate(interaction.guild_id, salvar)
        await interaction.followup.send(
            f"Painel publicado em {canal.mention}. Configure também /sugestao_canal.", ephemeral=True
        )


async def setup(bot):
    bot.add_view(PainelSugestoes())  # Painel público persistente.
    bot.add_view(PainelAdministrativo())  # Painel administrativo persistente.
    from modules.sugestoes.recovery import register_vote_views
    recovered = await register_vote_views(bot)
    print(f"[KING PLUS] {recovered} painéis de votação recuperados.")
    await bot.add_cog(Suggestions(bot))
