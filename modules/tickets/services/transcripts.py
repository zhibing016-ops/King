"""Safe HTML ticket transcript export. Requires Read Message History."""
import html
import io
from datetime import timezone
import discord

MAX_MESSAGES = 5000

def esc(value):
    return html.escape(str(value or ""), quote=True)

async def build_transcript(channel: discord.TextChannel) -> discord.File:
    records = []
    async for msg in channel.history(limit=MAX_MESSAGES, oldest_first=True):
        stamp = msg.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        attachments = "".join(
            f'<li><a href="{esc(a.url)}" rel="noopener noreferrer">{esc(a.filename)}</a></li>'
            for a in msg.attachments
        )
        text = esc(msg.content).replace("\\n", "<br>")
        records.append(
            f'<article><header><strong>{esc(msg.author.display_name)}</strong> '
            f'<small>{esc(stamp)} · ID {msg.id}</small></header>'
            f'<p>{text}</p>'
            + (f'<ul>{attachments}</ul>' if attachments else '') + '</article>'
        )
    document = (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Transcrição de ticket</title>'
        '<style>body{font-family:system-ui,sans-serif;background:#f6f7f9;color:#20242b;'
        'max-width:900px;margin:2rem auto;padding:1rem}article{background:white;'
        'border:1px solid #ddd;border-radius:10px;padding:1rem;margin:.6rem 0}'
        'p{white-space:normal;overflow-wrap:anywhere}small{color:#666}a{overflow-wrap:anywhere}</style>'
        '</head><body><h1>Transcrição do ticket</h1>'
        f'<p>Servidor: {esc(channel.guild.name)} | Canal: {esc(channel.name)}'
        f' | Canal ID: {channel.id}</p>'
        f'<p>Últimas até {MAX_MESSAGES} mensagens, em ordem cronológica. '
        'Anexos são registrados como links, não incorporados.</p>'
        + "".join(records) + '</body></html>'
    )
    return discord.File(io.BytesIO(document.encode("utf-8")),
                        filename=f"ticket-{channel.id}.html")

async def send_to_logs(channel: discord.TextChannel, actor: discord.abc.User,
                       reason: str = "") -> bool:
    from modules.tickets.config.storage import get_config
    cfg = await get_config(channel.guild.id)
    target = channel.guild.get_channel(int(cfg["log_channel_id"])) if cfg.get("log_channel_id") else None
    if not isinstance(target, discord.TextChannel):
        return False
    transcript = await build_transcript(channel)
    await target.send(
        content=f"📄 Transcrição do ticket `{channel.id}` | Ação: {actor} ({actor.id})"
                + (f" | Motivo: {reason[:300]}" if reason else ""),
        file=transcript,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    return True
