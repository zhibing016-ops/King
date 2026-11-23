"""Configuração, extensões e sincronização de comandos do KING PLUS."""
import logging
import os
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
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.reactions = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)

    async def setup_hook(self):
        failures = []
        for extension in EXTENSIONS:
            try:
                await self.load_extension(extension)
                LOG.info("OK: %s", extension)
            except Exception as exc:
                LOG.exception("Falha ao carregar %s", extension)
                failures.append((extension, str(exc)))

        for name in SUGGESTIONS_HELPERS:
            extension = "modules.sugestoes.cogs." + name
            before = {cmd.name for cmd in self.tree.get_commands()}
            try:
                await self.load_extension(extension)
                # Não remove os comandos dos outros sistemas.
                for command in list(self.tree.get_commands()):
                    if command.name not in before:
                        self.tree.remove_command(command.name)
                LOG.info("OK: %s (comandos legados ocultos)", extension)
            except Exception as exc:
                LOG.exception("Falha ao carregar %s", extension)
                failures.append((extension, str(exc)))
        try:
            await self.load_extension("modules.sugestoes.cogs.unified_panel")
        except Exception as exc:
            LOG.exception("Falha no painel de sugestões")
            failures.append(("sugestoes", str(exc)))

        if failures:
            LOG.warning("Extensões com falha: %s", failures)
        guild_id = (os.getenv("GUILD_ID") or "").strip()
        try:
            if guild_id:
                guild = discord.Object(id=int(guild_id))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
            else:
                synced = await self.tree.sync()
            LOG.info("Comandos sincronizados: %d", len(synced))
        except discord.Forbidden:
            LOG.exception("Sem acesso para sincronizar comandos: confira GUILD_ID, instalação do bot e escopo applications.commands")
        except Exception:
            LOG.exception("Falha ao sincronizar comandos")

    async def on_ready(self):
        LOG.info("KING PLUS conectado: %s", self.user)
