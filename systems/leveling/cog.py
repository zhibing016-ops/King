import logging
import discord
from discord import app_commands
from discord.ext import commands
from .storage import LevelStorage
from .backups import BackupManager
from .xp_manager import XPManager
from .progression import progress_from_xp, progress_bar
from .ranking import member_position
from .leaderboard import leaderboard_page, position_summary
from .cards.rank_card import make_rank_card, THEMES
import re
from .rewards import normalized_rewards, reward_changes
from .announcements import validate_template, render_announcement, DEFAULT_MESSAGE

log = logging.getLogger(__name__)

class Leveling(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.storage = LevelStorage()
        self.backups = BackupManager(self.storage)
        self.xp = XPManager()

    @app_commands.command(name="nivel", description="Abre a central administrativa de níveis")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def nivel_principal(self, interaction: discord.Interaction):
        from .panels.main_panel import MainPanel
        panel = MainPanel(self, interaction.user.id)
        await interaction.response.send_message(embed=await panel.embed(interaction), view=panel, ephemeral=True)

    @app_commands.command(name="perfil", description="Mostra seu perfil de nível ou o de outro membro")
    @app_commands.guild_only()
    @app_commands.describe(membro="Membro a consultar (opcional)")
    async def perfil_publico(self, interaction: discord.Interaction, membro: discord.Member | None = None):
        await self._send_rank_card(interaction, membro)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        checker = getattr(self.bot, "king_plus_system_enabled", None)
        if callable(checker) and not checker("leveling", message.guild.id):
            return
        try:
            data = await self.storage.get(message.guild.id)
            config = data["config"]
            if not self.xp.eligible(message, config):
                return
            member, previous_level = await self.storage.add_xp(
                message.guild.id, message.author.id, self.xp.amount(config)
            )
            if member["level"] > previous_level:
                log.info("Nível: guild=%s user=%s %s -> %s", message.guild.id, message.author.id, previous_level, member["level"])
                await self._sync_rewards(message.author, member["xp"], config)
                await self._announce_level_up(message, previous_level, member["level"], config)
        except (OSError, ValueError, TypeError) as exc:
            log.exception("Falha ao registrar XP no servidor %s: %s", message.guild.id, exc)

    async def _announce_level_up(self, message: discord.Message, previous_level: int, level: int, config: dict):
        if not config.get("announce_level_up", True):
            return
        channel_id = config.get("level_up_channel_id")
        channel = message.guild.get_channel(int(channel_id)) if channel_id else message.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            log.warning("Canal de anúncio indisponível no servidor %s", message.guild.id)
            return
        try:
            content = render_announcement(
                config.get("level_up_message", DEFAULT_MESSAGE),
                member_name=message.author.display_name,
                member_id=message.author.id,
                level=level,
                previous_level=previous_level,
                guild_name=message.guild.name,
            )
            allowed = discord.AllowedMentions(everyone=False, roles=False, users=[message.author], replied_user=False)
            if config.get("level_up_embed", True):
                embed = discord.Embed(description=content, color=discord.Color.gold())
                embed.set_author(name="KING PLUS • Subiu de nível!")
                await channel.send(embed=embed, allowed_mentions=allowed)
            else:
                await channel.send(content, allowed_mentions=allowed)
        except (ValueError, discord.Forbidden, discord.HTTPException):
            log.exception("Falha ao anunciar nível no servidor %s", message.guild.id)

    async def aviso_ativar(self, interaction: discord.Interaction, ativar: bool):
        await self.storage.update_config(interaction.guild_id, announce_level_up=ativar)
        await interaction.response.send_message("✅ Avisos de nível " + ("ativados." if ativar else "desativados."), ephemeral=True)

    async def aviso_canal(self, interaction: discord.Interaction, canal: discord.TextChannel | None = None):
        await self.storage.update_config(interaction.guild_id, level_up_channel_id=canal.id if canal else None)
        await interaction.response.send_message(f"✅ Canal de avisos: {canal.mention if canal else 'canal onde o XP foi ganho'}", ephemeral=True)

    async def aviso_mensagem(self, interaction: discord.Interaction, texto: str):
        try:
            validate_template(texto)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return
        await self.storage.update_config(interaction.guild_id, level_up_message=texto)
        await interaction.response.send_message("✅ Mensagem de nível atualizada.", ephemeral=True)

    async def aviso_estilo(self, interaction: discord.Interaction, usar_embed: bool):
        await self.storage.update_config(interaction.guild_id, level_up_embed=usar_embed)
        await interaction.response.send_message("✅ Estilo configurado: " + ("embed" if usar_embed else "texto") + ".", ephemeral=True)

    async def aviso_preview(self, interaction: discord.Interaction):
        config = (await self.storage.get(interaction.guild_id))["config"]
        content = render_announcement(config.get("level_up_message", DEFAULT_MESSAGE), member_name=interaction.user.display_name, member_id=interaction.user.id, level=10, previous_level=9, guild_name=interaction.guild.name)
        if config.get("level_up_embed", True):
            embed = discord.Embed(description=content, color=discord.Color.gold(), title="KING PLUS • Prévia")
            await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        else:
            await interaction.response.send_message("**Prévia:** " + content, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    async def _sync_rewards(self, member: discord.Member, xp: int, config: dict):
        if not member.guild.me.guild_permissions.manage_roles:
            log.warning("Permissão Gerenciar Cargos ausente em %s", member.guild.id)
            return
        add_ids, remove_ids = reward_changes(config, xp, (role.id for role in member.roles))
        manageable = lambda role: role is not None and not role.managed and role < member.guild.me.top_role
        add = [role for rid in add_ids if manageable(role := member.guild.get_role(rid))]
        remove = [role for rid in remove_ids if manageable(role := member.guild.get_role(rid))]
        try:
            if add:
                await member.add_roles(*add, reason="KING PLUS: recompensa por nível")
            if remove:
                await member.remove_roles(*remove, reason="KING PLUS: atualização de recompensas")
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Não foi possível atualizar recompensas do membro %s", member.id)

    async def recompensa_adicionar(self, interaction: discord.Interaction,
                                  nivel: app_commands.Range[int, 1, 10000], cargo: discord.Role):
        if cargo.is_default() or cargo.managed or cargo >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ Cargo não gerenciável pelo bot.", ephemeral=True)
            return
        data = await self.storage.get(interaction.guild_id)
        rewards = dict(data["config"].get("rewards", {}))
        rewards[str(nivel)] = cargo.id
        await self.storage.update_config(interaction.guild_id, rewards=rewards)
        await interaction.response.send_message(f"✅ Nível {nivel}: {cargo.mention}.", ephemeral=True)

    async def recompensa_remover(self, interaction: discord.Interaction,
                                nivel: app_commands.Range[int, 1, 10000]):
        data = await self.storage.get(interaction.guild_id)
        rewards = dict(data["config"].get("rewards", {}))
        if rewards.pop(str(nivel), None) is None:
            await interaction.response.send_message("❌ Não existe recompensa nesse nível.", ephemeral=True)
            return
        await self.storage.update_config(interaction.guild_id, rewards=rewards)
        await interaction.response.send_message("✅ Recompensa removida da configuração. Cargos já concedidos não são revogados automaticamente.", ephemeral=True)

    async def recompensa_modo(self, interaction: discord.Interaction, modo: app_commands.Choice[str]):
        await self.storage.update_config(interaction.guild_id, reward_mode=modo.value)
        await interaction.response.send_message(f"✅ Modo atualizado: {modo.name}. A mudança será aplicada nas próximas sincronizações.", ephemeral=True)

    async def recompensas(self, interaction: discord.Interaction):
        config = (await self.storage.get(interaction.guild_id))["config"]
        rewards = normalized_rewards(config)
        lines = [f"Nível **{level}**: <@&{role}>" for level, role in sorted(rewards.items())]
        await interaction.response.send_message("🏅 **Recompensas KING PLUS**\n" + ("\n".join(lines[:35]) or "Nenhuma recompensa configurada.") + f"\nModo: `{config.get('reward_mode', 'stack')}`", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    async def recompensa_sincronizar(self, interaction: discord.Interaction, membro: discord.Member):
        await interaction.response.defer(ephemeral=True)
        data = await self.storage.get(interaction.guild_id)
        xp = int(data["members"].get(str(membro.id), {}).get("xp", 0))
        await self._sync_rewards(membro, xp, data["config"])
        await interaction.followup.send("✅ Sincronização solicitada. Verifique as permissões e a hierarquia dos cargos.", ephemeral=True)

    async def _send_rank_card(self, interaction: discord.Interaction, membro: discord.Member | None = None):
        await interaction.response.defer(thinking=True)
        target = membro or interaction.user
        data = await self.storage.get(interaction.guild_id)
        record = data["members"].get(str(target.id), {"xp": 0})
        xp = int(record["xp"])
        position = member_position(data, target.id)
        config = data["config"]
        avatar_bytes = None
        try:
            avatar_bytes = await target.display_avatar.replace(size=128, format="png").read()
        except (discord.HTTPException, AttributeError, ValueError):
            pass
        background_bytes = None
        bg = config.get("rank_background")
        if bg:
            try:
                import base64
                background_bytes = base64.b64decode(bg, validate=True)
            except (ValueError, TypeError): pass
        image = await __import__("asyncio").to_thread(
            make_rank_card, target.display_name, xp, position,
            theme=config.get("rank_theme", "dark"), accent=config.get("rank_accent"),
            avatar_bytes=avatar_bytes, background_bytes=background_bytes)
        await interaction.followup.send(file=discord.File(image, filename="king_plus_rank.png"))

    async def rank(self, interaction: discord.Interaction, membro: discord.Member | None = None):
        await self._send_rank_card(interaction, membro)

    async def perfil(self, interaction: discord.Interaction, membro: discord.Member | None = None):
        await self._send_rank_card(interaction, membro)

    async def tema(self, interaction: discord.Interaction, tema: app_commands.Choice[str]):
        await self.storage.update_config(interaction.guild_id, rank_theme=tema.value)
        await interaction.response.send_message(f"✅ Tema alterado para **{tema.name}**.", ephemeral=True)

    async def cor(self, interaction: discord.Interaction, hexadecimal: str):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", hexadecimal):
            return await interaction.response.send_message("Use uma cor no formato #RRGGBB.", ephemeral=True)
        await self.storage.update_config(interaction.guild_id, rank_accent=hexadecimal)
        await interaction.response.send_message("✅ Cor atualizada.", ephemeral=True)

    async def fundo(self, interaction: discord.Interaction, imagem: discord.Attachment):
        await interaction.response.defer(ephemeral=True)
        if imagem.size > 1_000_000 or imagem.content_type not in ("image/png", "image/jpeg"):
            return await interaction.followup.send("Envie PNG/JPEG de até 1 MB.", ephemeral=True)
        raw = await imagem.read()
        from PIL import Image
        from io import BytesIO
        try:
            with Image.open(BytesIO(raw)) as img:
                img.verify()
            with Image.open(BytesIO(raw)) as img:
                if img.width * img.height > 12_000_000: raise ValueError()
        except (OSError, ValueError):
            return await interaction.followup.send("Imagem inválida ou muito grande.", ephemeral=True)
        import base64
        await self.storage.update_config(interaction.guild_id, rank_background=base64.b64encode(raw).decode("ascii"))
        await interaction.followup.send("✅ Fundo atualizado. Use /rank para visualizar.", ephemeral=True)

    async def fundo_remover(self, interaction: discord.Interaction):
        await self.storage.update_config(interaction.guild_id, rank_background=None)
        await interaction.response.send_message("✅ Fundo removido.", ephemeral=True)

    async def rank_preview(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data = await self.storage.get(interaction.guild_id)
        cfg = data["config"]
        import base64, asyncio
        bg = base64.b64decode(cfg["rank_background"]) if cfg.get("rank_background") else None
        img = await asyncio.to_thread(make_rank_card, interaction.user.display_name, 3000, 3,
                                      theme=cfg.get("rank_theme", "dark"), accent=cfg.get("rank_accent"), background_bytes=bg)
        await interaction.followup.send(file=discord.File(img, filename="rank_preview.png"), ephemeral=True)

    async def consultar(self, interaction: discord.Interaction, membro: discord.Member | None = None):
        target = membro or interaction.user
        data = await self.storage.get_member(interaction.guild_id, target.id)
        progress = progress_from_xp(data["xp"])
        embed = discord.Embed(title="🏆 KING PLUS • Nível", color=discord.Color.blurple())
        embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
        embed.add_field(name="Nível", value=str(progress["level"]))
        embed.add_field(name="XP total", value=f'{progress["xp"]:,}'.replace(",", "."))
        embed.add_field(name="Próximo nível", value=str(progress["level"] + 1))
        embed.add_field(name="Progresso", inline=False,
            value=f'{progress_bar(progress["current_level_xp"], progress["level_span_xp"])} '
                  f'{progress["percent"]:.1f}%\n'
                  f'{progress["current_level_xp"]}/{progress["level_span_xp"]} XP neste nível '
                  f'• faltam {progress["remaining_xp"]} XP')
        await interaction.response.send_message(embed=embed)

    async def progresso(self, interaction: discord.Interaction, membro: discord.Member | None = None):
        target = membro or interaction.user
        data = await self.storage.get_member(interaction.guild_id, target.id)
        progress = progress_from_xp(data["xp"])
        await interaction.response.send_message(
            f'📈 **{target.display_name}** • nível **{progress["level"]}** → **{progress["level"] + 1}**\n'
            f'{progress_bar(progress["current_level_xp"], progress["level_span_xp"])} '
            f'{progress["percent"]:.1f}%\n'
            f'Faltam **{progress["remaining_xp"]} XP** para subir de nível.')


    def _ranking_embed(self, guild: discord.Guild, data: dict, page: int) -> discord.Embed:
        result = leaderboard_page(data, page)
        embed = discord.Embed(title="🏆 KING PLUS • Ranking de XP", color=discord.Color.gold())
        if not result["rows"]:
            embed.description = "Ainda não há membros com XP registrado."
        else:
            lines = []
            for position, user_id, xp in result["rows"]:
                member = guild.get_member(user_id)
                label = discord.utils.escape_markdown(member.display_name) if member else f"Usuário {user_id}"
                lines.append(f"**#{position}** • {label} — **{xp:,} XP**".replace(",", "."))
            embed.description = "\n".join(lines)
        embed.set_footer(text=f'Página {result["page"]}/{result["pages"]} • {result["total"]} membros com registro')
        return embed

    async def ranking(self, interaction: discord.Interaction, pagina: app_commands.Range[int, 1, 100000] = 1):
        data = await self.storage.get(interaction.guild_id)
        result = leaderboard_page(data, pagina)
        view = RankingView(self, interaction.user.id, data, result["page"])
        await interaction.response.send_message(embed=self._ranking_embed(interaction.guild, data, result["page"]), view=view)

    async def posicao(self, interaction: discord.Interaction, membro: discord.Member | None = None):
        target = membro or interaction.user
        data = await self.storage.get(interaction.guild_id)
        summary = position_summary(data, target.id)
        if summary["position"] is None:
            message = f"📊 {target.mention} ainda não tem XP registrado no ranking."
        else:
            message = (f'📊 {target.mention} está em **#{summary["position"]}** de '
                       f'**{summary["total"]}** membros, com **{summary["xp"]:,} XP**.').replace(",", ".")
        await interaction.response.send_message(message, allowed_mentions=discord.AllowedMentions.none())

    async def painel(self, interaction: discord.Interaction):
        from .panels.admin_panel import AdminPanel
        view = AdminPanel(self, interaction.user.id)
        await interaction.response.send_message(embed=await view.show(interaction), view=view, ephemeral=True)

    async def backup(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        name = await self.backups.create(interaction.guild.id)
        await interaction.followup.send(f"Backup criado: `{name}`", ephemeral=True)

    async def backups_list(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        names = await self.backups.list(interaction.guild.id)
        await interaction.response.send_message("\n".join(f"`{n}`" for n in names[:10]) or "Nenhum backup.", ephemeral=True)

    async def restaurar(self, interaction: discord.Interaction, arquivo: str, confirmar: bool = False):
        if not interaction.guild:
            return await interaction.response.send_message("Use em um servidor.", ephemeral=True)
        if not confirmar:
            return await interaction.response.send_message("A restauração substitui o progresso atual. Execute novamente com `confirmar: True`.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            safety = await self.backups.restore(interaction.guild.id, arquivo)
        except (ValueError, FileNotFoundError, OSError) as exc:
            return await interaction.followup.send(f"Falha na restauração: {exc}", ephemeral=True)
        await interaction.followup.send(f"Backup restaurado. Cópia de segurança anterior: `{safety}`", ephemeral=True)

    async def status(self, interaction: discord.Interaction):
        config = (await self.storage.get(interaction.guild_id))["config"]
        embed = discord.Embed(title="🏆 KING PLUS • Sistema de Níveis", color=discord.Color.blurple())
        embed.add_field(name="Estado", value="🟢 Ativado" if config["enabled"] else "🔴 Desativado")
        embed.add_field(name="XP por mensagem", value=f'{config["xp_per_message_min"]}–{config["xp_per_message_max"]}')
        embed.add_field(name="Cooldown", value=f'{config["cooldown_seconds"]} segundos')
        embed.add_field(name="Canais ignorados", value=str(len(config["ignored_channel_ids"])))
        embed.add_field(name="Cargos ignorados", value=str(len(config["ignored_role_ids"])))
        embed.set_footer(text="Fase 7 • XP, ranking, cargos e anúncios")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def ativar(self, interaction: discord.Interaction):
        await self.storage.update_config(interaction.guild_id, enabled=True)
        await interaction.response.send_message("✅ Sistema de níveis ativado. O XP automático está funcionando!", ephemeral=True)

    async def desativar(self, interaction: discord.Interaction):
        await self.storage.update_config(interaction.guild_id, enabled=False)
        await interaction.response.send_message("🛠️ Sistema de níveis desativado.", ephemeral=True)

    async def configurarxp(self, interaction: discord.Interaction,
                          minimo: app_commands.Range[int, 1, 1000],
                          maximo: app_commands.Range[int, 1, 1000],
                          cooldown: app_commands.Range[int, 5, 3600]):
        if minimo > maximo:
            await interaction.response.send_message("❌ O XP mínimo deve ser menor ou igual ao máximo.", ephemeral=True)
            return
        await self.storage.update_config(interaction.guild_id,
            xp_per_message_min=minimo, xp_per_message_max=maximo, cooldown_seconds=cooldown)
        await interaction.response.send_message(f"✅ XP: {minimo}–{maximo}; cooldown: {cooldown}s.", ephemeral=True)

    async def ignorarcanal(self, interaction: discord.Interaction, canal: discord.TextChannel, ignorar: bool):
        data = await self.storage.get(interaction.guild_id)
        ids = set(data["config"]["ignored_channel_ids"])
        (ids.add if ignorar else ids.discard)(canal.id)
        await self.storage.update_config(interaction.guild_id, ignored_channel_ids=sorted(ids))
        await interaction.response.send_message("✅ Filtro de canal atualizado.", ephemeral=True)

    async def ignorarcargo(self, interaction: discord.Interaction, cargo: discord.Role, ignorar: bool):
        data = await self.storage.get(interaction.guild_id)
        ids = set(data["config"]["ignored_role_ids"])
        (ids.add if ignorar else ids.discard)(cargo.id)
        await self.storage.update_config(interaction.guild_id, ignored_role_ids=sorted(ids))
        await interaction.response.send_message("✅ Filtro de cargo atualizado.", ephemeral=True)

class RankingView(discord.ui.View):
    def __init__(self, cog: Leveling, owner_id: int, data: dict, page: int):
        super().__init__(timeout=180)
        self.cog, self.owner_id, self.data, self.page = cog, owner_id, data, page
        self._update_buttons()

    def _update_buttons(self):
        result = leaderboard_page(self.data, self.page)
        self.page = result["page"]
        self.previous.disabled = self.page <= 1
        self.next.disabled = self.page >= result["pages"]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Somente quem abriu o ranking pode navegar. Abra o ranking pelo painel /nivel.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Anterior", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.cog._ranking_embed(interaction.guild, self.data, self.page), view=self)

    @discord.ui.button(label="Próxima", emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.cog._ranking_embed(interaction.guild, self.data, self.page), view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        # Sem edição remota no timeout: a visualização expira e botões deixam de responder.


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
