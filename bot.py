"""Configuração, extensões e sincronização de comandos do KING PLUS."""
import logging
import os
import sys
import time
import platform
import traceback
from pathlib import Path
import discord
from discord.ext import commands

LOG = logging.getLogger("kingplus")

# Cada extensão tem comando próprio; nenhuma central /kingplus é carregada.
EXTENSIONS = [
    "modules.tickets.cog",
    "modules.enquetes.cog",
    "systems.leveling.cog",
    "systems.reaction_roles.cog",
    "modules.moderacao.kingplus_moderation",
    "modules.redeem.cog",
    "systems.giveaways.cog",
    "modules.mu.mu",
    "modules.mu.listas",
    "modules.mu.alarmes",
    "controle_central.cog",
]

# Sugestões: os cogs auxiliares são carregados para que os botões do painel
# funcionem; seus slash commands legados são removidos em favor de /sugestao.
SUGGESTIONS_HELPERS = [
    "suggestions", "queue", "team", "dm_settings", "audit_panel",
    "discussion_settings", "antispam_settings", "metrics_panel",
    "appearance_panel", "activity_panel", "maintenance_panel",
]

class KingPlus(commands.Bot):
    def __init__(self):
        self.started_at = time.monotonic()
        self.diagnostics = []
        self.sync_ok = False
        self.synced_count = 0
        self.ready_count = 0
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.reactions = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)

    async def interaction_check(self, interaction):
        """Bloqueio de slash commands; eventos e botões exigem checagem específica."""
        manager = getattr(self, "system_manager", None)
        if manager is None or interaction.command is None:
            return True
        from controle_central.cog import ROUTES
        key = ROUTES.get(interaction.command.qualified_name.split()[0])
        if key and not manager.is_enabled(key):
            await interaction.response.send_message("🔧 Este sistema está temporariamente em manutenção.", ephemeral=True)
            return False
        return True

    def report_error(self, context, exc):
        root = exc
        while getattr(root, "original", None) is not None and root.original is not root:
            root = root.original
        frames = traceback.extract_tb(root.__traceback__)
        location = frames[-1] if frames else None
        hints = {
            "ModuleNotFoundError": "Confira a dependência ou o caminho do módulo.",
            "ImportError": "Confira imports, versões e possíveis dependências circulares.",
            "CommandLimitReached": "Confira os limites de comandos do Discord.",
            "Forbidden": "Confira permissões, hierarquia de cargos e instalação do bot.",
            "NotFound": "Confira se o recurso ainda existe.",
            "HTTPException": "Confira a resposta da API e a conectividade.",
            "JSONDecodeError": "Confira a integridade do JSON antes de restaurar um backup.",
        }
        LOG.error("[ERRO] %s | %s: %s | arquivo=%s | linha=%s | função=%s | orientação=%s",
                  context, type(root).__name__, root,
                  location.filename if location else "indisponível",
                  location.lineno if location else "?",
                  location.name if location else "?",
                  hints.get(type(root).__name__, "Consulte o traceback completo."),
                  exc_info=(type(exc), exc, exc.__traceback__))

    async def load_diagnostic(self, extension, hide_legacy=False):
        start = time.monotonic()
        before = {cmd.name for cmd in self.tree.get_commands()}
        try:
            await self.load_extension(extension)
            removed = []
            if hide_legacy:
                for command in list(self.tree.get_commands()):
                    if command.name not in before:
                        self.tree.remove_command(command.name)
                        removed.append(command.name)
            elapsed = time.monotonic() - start
            self.diagnostics.append((extension, True, elapsed))
            LOG.info("[OK] %s | %.3fs | legados ocultos=%d", extension, elapsed, len(removed))
        except Exception as exc:
            self.diagnostics.append((extension, False, time.monotonic() - start))
            self.report_error("Carregamento: " + extension, exc)

    async def setup_hook(self):
        LOG.info("========== KING PLUS | DIAGNOSTICO V2 ==========")
        LOG.info("Python %s | discord.py %s | %s", platform.python_version(), discord.__version__, platform.system())
        LOG.info("Executável: %s | Projeto: %s", sys.executable, Path(__file__).resolve().parent)
        async def guard(interaction):
            return await self.interaction_check(interaction)
        self.tree.interaction_check = guard
        original_tree_error = self.tree.on_error
        async def tree_error(interaction, error):
            self.report_error("Slash: " + str(getattr(interaction.command, "qualified_name", "desconhecido")), error)
            await original_tree_error(interaction, error)
        self.tree.on_error = tree_error
        for extension in EXTENSIONS:
            await self.load_diagnostic(extension)
        for name in SUGGESTIONS_HELPERS:
            await self.load_diagnostic("modules.sugestoes.cogs." + name, hide_legacy=True)
        await self.load_diagnostic("modules.sugestoes.cogs.unified_panel")
        guild_id = (os.getenv("GUILD_ID") or "").strip()
        try:
            if guild_id:
                guild = discord.Object(id=int(guild_id))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
            else:
                synced = await self.tree.sync()
            self.sync_ok = True
            self.synced_count = len(synced)
            LOG.info("[OK] Sincronização %s: %d comandos", "servidor" if guild_id else "global", len(synced))
            LOG.info("Comandos: %s", ", ".join("/" + cmd.name for cmd in synced))
        except Exception as exc:
            self.report_error("Sincronização de comandos", exc)
        failures = [name for name, ok, _ in self.diagnostics if not ok]
        LOG.info("========== RESUMO ==========")
        LOG.info("Extensões: %d/%d | Falhas: %d | Cogs: %d", len(self.diagnostics)-len(failures), len(self.diagnostics), len(failures), len(self.cogs))
        if failures:
            LOG.warning("Extensões com falha: %s", ", ".join(failures))
        LOG.info("Sincronização: %s | Tempo setup: %.2fs", "OK" if self.sync_ok else "FALHA", time.monotonic()-self.started_at)

    async def on_ready(self):
        self.ready_count += 1
        healthy = self.sync_ok and all(ok for _, ok, _ in self.diagnostics)
        LOG.info("========== %s ==========", "ONLINE" if healthy else "ONLINE COM FALHAS")
        LOG.info("KING PLUS conectado: %s | Servidores: %d | Latência: %.0f ms", self.user, len(self.guilds), self.latency*1000)
        LOG.info("Eventos READY: %d | Tempo desde início: %.2fs", self.ready_count, time.monotonic()-self.started_at)

    async def on_disconnect(self):
        LOG.warning("[CONEXÃO] Gateway desconectado; aguardando reconexão.")

    async def on_resumed(self):
        LOG.info("[CONEXÃO] Sessão retomada.")

    async def on_error(self, event_method, *args, **kwargs):
        exc = sys.exc_info()[1]
        if exc is not None:
            self.report_error("Evento: " + event_method, exc)

    async def on_command_error(self, context, exception):
        if context.command and context.command.has_error_handler():
            return
        if context.cog and context.cog.has_error_handler():
            return
        self.report_error("Comando prefixado: " + str(context.command), exception)

