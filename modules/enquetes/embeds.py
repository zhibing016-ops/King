import discord
from .manager import counts

def render(p):
    embed=discord.Embed(title="📊 "+p["question"], color=discord.Color(int(p.get("color",0x5865F2))))
    c=counts(p); total=sum(c)
    if p.get("hide_results") and p["status"]=="open":
        embed.description="Resultados ocultos até o encerramento."
        return embed
    for i,(option,n) in enumerate(zip(p["options"],c)):
        pct=round(n*100/total) if total else 0
        embed.add_field(name=f"{i+1}. {option}", value=f"{'█'*(pct//10)}{'░'*(10-pct//10)} {pct}% · {n} voto(s)", inline=False)
    embed.set_footer(text=f"ID: {p['id']} · {p['status']} · {len(p['votes'])} participante(s)")
    if p.get("image"): embed.set_image(url=p["image"])
    if p.get("thumbnail"): embed.set_thumbnail(url=p["thumbnail"])
    return embed
