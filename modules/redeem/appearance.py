"""Visual customization, scoped by Discord guild."""
import re
from urllib.parse import urlsplit
import discord
from modules.redeem.store import load, save

DEFAULT = {
    "title": "🎁 KING PLUS | Resgate de códigos",
    "description": "Clique em **Claim**, escolha seu jogo e preencha o formulário.\nO registro **não garante entrega de recompensas**.",
    "color": "#2ECC71", "footer": "KING PLUS • Redeem Codes",
    "image": "", "thumbnail": "", "claim_label": "Claim",
    "claim_emoji": "🎟️", "claim_style": "green",
}
STYLES = {"green": discord.ButtonStyle.success, "blue": discord.ButtonStyle.primary,
          "gray": discord.ButtonStyle.secondary, "red": discord.ButtonStyle.danger}

def get_theme(guild_id):
    stored = load().get("settings", {}).get(str(guild_id), {}).get("appearance", {})
    return {**DEFAULT, **stored}

def validate_url(value):
    if not value: return ""
    p = urlsplit(value)
    if p.scheme != "https" or not p.hostname or p.username or p.password or len(value) > 500:
        raise ValueError("A imagem precisa usar URL HTTPS pública válida.")
    if p.hostname.lower() in ("localhost",) or p.hostname.lower().endswith((".local", ".internal")):
        raise ValueError("Endereço interno não permitido.")
    return value

def update_theme(guild_id, **changes):
    theme = {**get_theme(guild_id), **changes}
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", theme["color"]):
        raise ValueError("Cor inválida: use #RRGGBB.")
    if theme["claim_style"] not in STYLES:
        raise ValueError("Estilo inválido: green, blue, gray ou red.")
    for field in ("image", "thumbnail"):
        theme[field] = validate_url(theme[field].strip())
    if not theme["title"].strip() or not theme["claim_label"].strip():
        raise ValueError("Título e texto do botão são obrigatórios.")
    data = load()
    data.setdefault("settings", {}).setdefault(str(guild_id), {})["appearance"] = theme
    save(data)

def reset_theme(guild_id):
    data = load()
    data.setdefault("settings", {}).setdefault(str(guild_id), {}).pop("appearance", None)
    save(data)

def make_public_embed(guild_id):
    t = get_theme(guild_id)
    e = discord.Embed(title=t["title"], description=t["description"],
                      color=int(t["color"][1:], 16))
    if t["footer"]: e.set_footer(text=t["footer"])
    if t["image"]: e.set_image(url=t["image"])
    if t["thumbnail"]: e.set_thumbnail(url=t["thumbnail"])
    return e

def make_dashboard_embed(guild_id, games, apis):
    return discord.Embed(title="🎮 KING PLUS | Redeem Codes",
        description=f"**Jogos cadastrados:** {games}\n**APIs configuradas:** {apis}\n\nGerencie seus jogos pelos botões abaixo.\n\n*Fase 12 — Personalização avançada.*",
        color=discord.Color.blurple())

def button_theme(button, guild_id):
    t = get_theme(guild_id)
    button.label = t["claim_label"]
    button.style = STYLES[t["claim_style"]]
    if t["claim_emoji"]:
        try: button.emoji = t["claim_emoji"]
        except (TypeError, ValueError): button.emoji = "🎟️"
    else:
        button.emoji = None
