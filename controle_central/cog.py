"""Controle Central independente do KING PLUS. /controle é o único comando novo."""
import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands

BASE = Path(__file__).resolve().parent
SYSTEMS = BASE / "systems.json"
SETTINGS = BASE / "settings.json"
AUDIT = BASE / "audit.jsonl"

# Mapeamento dos comandos reais. Comandos não identificados não são bloqueados.
ROUTES = {
    "ticket": "tickets", "tickets": "tickets", "enquete": "enquetes",
    "nivel": "niveis", "rank": "niveis", "reactionroles": "cargos_reacao",
    "reacao": "cargos_reacao", "sorteio": "sorteios", "giveaway": "sorteios",
    "moderacao": "moderacao", "automod": "automod", "redeem": "redeem",
    "mu": "mu", "sugestao": "sugestoes",
}

class Manager:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.systems = json.loads(SYSTEMS.read_text(encoding="utf-8"))

    def is_enabled(self, key):
        return self.systems.get(key, {}).get("enabled", True)

    async def toggle(self, key):
        async with self.lock:
            value = not self.systems[key]["enabled"]
            new = {k: dict(v) for k, v in self.systems.items()}
            new[key]["enabled"] = value
            atomic_json(SYSTEMS, new)
            self.systems = new
            return value

def atomic_json(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)

def settings():
    return json.loads(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.exists() else {}

def save_setting(key, value):
    data = settings()
    data[key] = value
    atomic_json(SETTINGS, data)

async def log_event(bot, actor, action, system=None):
    event = {"at": datetime.now(timezone.utc).isoformat(), "actor": str(actor), "action": action, "system": system}
    with AUDIT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    channel_id = settings().get("logs_channel_id")
    if channel_id:
        try:
            channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
            await channel.send(f"🛡️ Controle Central: {action} • {system or '-'} • ID {actor}", allowed_mentions=discord.AllowedMentions.none())
        except (discord.HTTPException, AttributeError):
            pass

async def notice(bot, key, enabled):
    channel_id = settings().get("notice_channel_id")
    if not channel_id:
        return "Canal de avisos ainda não configurado."
    system = bot.system_manager.systems[key]
    title = "✅ Manutenção concluída" if enabled else "🔧 Sistema em manutenção"
    desc = f"{system['emoji']} **{system['name']}** {'ativado com sucesso' if enabled else 'desativado temporariamente'}."
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        await channel.send(embed=discord.Embed(title=title, description=desc), allowed_mentions=discord.AllowedMentions.none())
        return "Aviso publicado."
    except (discord.HTTPException, AttributeError):
        return "Não foi possível publicar aviso; confira as permissões."

def embed(manager):
    description = "\n".join(f"{s['emoji']} **{s['name']}** — {'🟢 Ativo' if s['enabled'] else '🔴 Manutenção'}" for s in manager.systems.values())
    return discord.Embed(title="⚙️ KING PLUS • Controle Central", description=description, color=discord.Color.blurple())

async def owner_only(interaction):
    owner_id = os.getenv("OWNER_ID", "").strip()
    if (owner_id.isdigit() and interaction.user.id == int(owner_id)) or await interaction.client.is_owner(interaction.user):
        return True
    await interaction.response.send_message("⛔ Apenas o dono do bot pode usar o Controle Central.", ephemeral=True)
    return False

class Confirm(discord.ui.View):
    def __init__(self, key, previous):
        super().__init__(timeout=120)
        self.key, self.previous = key, previous

    @discord.ui.button(label="Confirmar alteração", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        if not await owner_only(interaction):
            return
        manager = interaction.client.system_manager
        if manager.is_enabled(self.key) != self.previous:
            await interaction.response.edit_message(content="Estado alterado. Abra /controle novamente.", view=None)
            return
        await interaction.response.defer(ephemeral=True)
        enabled = await manager.toggle(self.key)
        await log_event(interaction.client, interaction.user.id, "ativado" if enabled else "desativado", self.key)
        result = await notice(interaction.client, self.key, enabled)
        await interaction.edit_original_response(content=f"✅ Estado atualizado. {result}", view=None)

class SystemSelect(discord.ui.Select):
    def __init__(self, manager):
        options = [discord.SelectOption(label=s['name'], value=key, emoji=s['emoji'], description="Ativo" if s['enabled'] else "Em manutenção") for key, s in manager.systems.items()]
        super().__init__(placeholder="Escolha um sistema para ativar/desativar", options=options)

    async def callback(self, interaction):
        if not await owner_only(interaction):
            return
        key = self.values[0]
        manager = interaction.client.system_manager
        current = manager.is_enabled(key)
        await interaction.response.send_message(f"Confirma {'desativar' if current else 'ativar'} **{manager.systems[key]['name']}**?", view=Confirm(key, current), ephemeral=True)

class ChannelModal(discord.ui.Modal, title="Configurar canal por ID"):
    channel_id = discord.ui.TextInput(label="ID do canal de texto", placeholder="123456789012345678")
    def __init__(self, setting_key):
        super().__init__()
        self.setting_key = setting_key

    async def on_submit(self, interaction):
        if not await owner_only(interaction):
            return
        try:
            cid = int(self.channel_id.value.strip())
            channel = interaction.client.get_channel(cid) or await interaction.client.fetch_channel(cid)
            if not isinstance(channel, discord.TextChannel) or not interaction.guild or channel.guild.id != interaction.guild.id:
                raise ValueError("Canal inválido")
            permissions = channel.permissions_for(interaction.guild.me)
            if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
                raise ValueError("Permissões insuficientes")
        except (ValueError, discord.HTTPException, AttributeError):
            await interaction.response.send_message("❌ Canal inválido ou sem permissões necessárias.", ephemeral=True)
            return
        save_setting(self.setting_key, cid)
        await log_event(interaction.client, interaction.user.id, "configuracao_canal", self.setting_key)
        await interaction.response.send_message(f"✅ Canal configurado: {channel.mention}", ephemeral=True)

class Panel(discord.ui.View):
    def __init__(self, manager):
        super().__init__(timeout=900)
        self.add_item(SystemSelect(manager))

    @discord.ui.button(label="Atualizar", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction, button):
        if await owner_only(interaction):
            await interaction.response.edit_message(embed=embed(interaction.client.system_manager), view=Panel(interaction.client.system_manager))

    @discord.ui.button(label="Canal de avisos", style=discord.ButtonStyle.primary, row=1)
    async def notices(self, interaction, button):
        if await owner_only(interaction):
            await interaction.response.send_modal(ChannelModal("notice_channel_id"))

    @discord.ui.button(label="Canal de logs", style=discord.ButtonStyle.primary, row=1)
    async def logs_channel(self, interaction, button):
        if await owner_only(interaction):
            await interaction.response.send_modal(ChannelModal("logs_channel_id"))

    @discord.ui.button(label="Ver logs", style=discord.ButtonStyle.secondary, row=2)
    async def logs(self, interaction, button):
        if not await owner_only(interaction):
            return
        if not AUDIT.exists():
            await interaction.response.send_message("Nenhum registro ainda.", ephemeral=True)
            return
        lines = AUDIT.read_text(encoding="utf-8").splitlines()[-8:]
        await interaction.response.send_message("🛡️ Últimas ações\n" + "\n".join(f"{json.loads(line)['at'][:16]} • {json.loads(line)['action']} • {json.loads(line).get('system') or '-'}" for line in lines), ephemeral=True)

class ControlCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="controle", description="Painel independente do Controle Central KING PLUS")
    @app_commands.guild_only()
    async def controle(self, interaction: discord.Interaction):
        if await owner_only(interaction):
            await interaction.response.send_message(embed=embed(self.bot.system_manager), view=Panel(self.bot.system_manager), ephemeral=True)

async def setup(bot):
    bot.system_manager = Manager()
    await bot.add_cog(ControlCog(bot))
