"""Aparência de embeds, por servidor. URLs são referências externas, não uploads."""
from urllib.parse import urlsplit
import ipaddress
import discord

DEFAULTS = {
    "panel_title": "💡 KING PLUS • Central de Sugestões",
    "panel_description": "Sua opinião ajuda a melhorar nosso servidor!\n\nClique em **Enviar sugestão** ou **Enviar anonimamente** para abrir o formulário.",
    "panel_color": "5865F2", "panel_footer": "KING PLUS • Sugestões",
    "panel_image": "", "panel_thumbnail": "",
    "suggestion_color": "5865F2", "suggestion_footer": "",
}

def valid_url(value):
    if not value: return True
    if len(value) > 500: return False
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password: return False
        host = parsed.hostname.lower()
        if host in ("localhost",) or host.endswith((".local", ".internal")): return False
        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_global: return False
        except ValueError: pass
        return True
    except ValueError: return False

def color_hex(value):
    raw = value.strip().lstrip("#")
    if len(raw) != 6 or any(c not in "0123456789abcdefABCDEF" for c in raw):
        raise ValueError("Cor inválida. Use hexadecimal de 6 dígitos, como #5865F2.")
    return raw.upper()

def theme(data):
    return {**DEFAULTS, **data.get("settings", {}).get("appearance", {})}

def panel_embed(t):
    e = discord.Embed(title=t["panel_title"], description=t["panel_description"], color=int(t["panel_color"], 16))
    if t["panel_footer"]: e.set_footer(text=t["panel_footer"])
    if t["panel_image"]: e.set_image(url=t["panel_image"])
    if t["panel_thumbnail"]: e.set_thumbnail(url=t["panel_thumbnail"])
    return e
