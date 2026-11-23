"""Guarda central para comandos slash e componentes de sistemas integrados."""
import json
from pathlib import Path
import discord
from discord import app_commands

MAP_FILE = Path(__file__).resolve().parent.parent / "config" / "interaction_routes.json"

class SystemGuard:
    def __init__(self, manager):
        self.manager = manager
        self.routes = json.loads(MAP_FILE.read_text(encoding="utf-8"))
        for route_type in ("slash_commands", "component_prefixes"):
            for route, key in self.routes.get(route_type, {}).items():
                if key not in manager.systems:
                    raise ValueError(f"Rota {route!r} aponta para sistema inexistente: {key!r}")

    def system_for_command(self, name):
        return self.routes.get("slash_commands", {}).get(name)

    def system_for_component(self, custom_id):
        matches = [(prefix, system) for prefix, system in self.routes.get("component_prefixes", {}).items() if custom_id.startswith(prefix)]
        return max(matches, key=lambda pair: len(pair[0]))[1] if matches else None

    def allowed(self, key):
        return key is None or self.manager.is_enabled(key)

    async def reject(self, interaction):
        message = "🔧 Este sistema está temporariamente em manutenção. Tente novamente mais tarde."
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)


def system_enabled(key):
    """Decorator para app_commands.command de módulos futuros.

    Exemplo:
        @app_commands.command(name="ticket")
        @system_enabled("tickets")
        async def ticket(self, interaction): ...
    """
    async def predicate(interaction: discord.Interaction):
        if interaction.client.system_manager.is_enabled(key):
            return True
        await interaction.client.system_guard.reject(interaction)
        return False
    return app_commands.check(predicate)
