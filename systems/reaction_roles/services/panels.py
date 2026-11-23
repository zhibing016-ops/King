"""Operações de painel. Identificadores gerados no servidor; JSON por guild."""
import re
import secrets
from urllib.parse import urlsplit
from datetime import datetime, timezone

HEX_COLOR = re.compile(r'^#?[0-9a-fA-F]{6}$')
MAX_PANELS = 25

def parse_color(value: str) -> int:
    value = value.strip()
    if not HEX_COLOR.fullmatch(value):
        raise ValueError('Cor inválida. Use #5865F2 (6 dígitos hexadecimais).')
    return int(value.lstrip('#'), 16)

def validate_customization(title, description, color, thumbnail='', image='', footer=''):
    title, description, footer = title.strip(), description.strip(), footer.strip()
    if not 1 <= len(title) <= 256 or not 1 <= len(description) <= 4000 or len(footer) > 2048:
        raise ValueError('Título, descrição ou rodapé excede o limite.')
    for url in (thumbnail, image):
        if url:
            parsed = urlsplit(url.strip())
            if len(url) > 2000 or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('Imagens exigem URLs HTTPS válidas.')
    return dict(title=title, description=description, color=parse_color(color),
                thumbnail_url=thumbnail.strip(), image_url=image.strip(), footer_text=footer)

def panel_embed(discord, panel):
    embed = discord.Embed(title=panel['title'], description=panel['description'], color=panel['color'])
    instructions = {'reactions': 'Reaja para escolher cargos', 'buttons': 'Clique nos botões para escolher cargos',
                    'select': 'Escolha os cargos no menu'}
    embed.set_footer(text=panel.get('footer_text') or 'KING PLUS • ' + instructions.get(panel.get('interface', 'reactions'), 'Cargos'))
    if panel.get('thumbnail_url'):
        embed.set_thumbnail(url=panel['thumbnail_url'])
    if panel.get('image_url'):
        embed.set_image(url=panel['image_url'])
    if panel.get('roles'):
        embed.add_field(name='Cargos disponíveis', value='\n'.join(f'{emoji} → <@&{role}>' for emoji,role in list(panel['roles'].items())[:20]), inline=False)
    if panel.get('temporary_seconds'):
        embed.add_field(name='⏱️ Temporário', value=f"Duração: {panel['temporary_seconds']//60} minutos", inline=False)
    if panel.get('unique'):
        embed.add_field(name='🔐 Unique', value='Um cargo por painel', inline=False)
    return embed

async def save_customization(store, guild_id, panel_id, values):
    def change(data):
        panel = data.get('panels', {}).get(panel_id)
        if panel is None:
            raise ValueError('Painel não encontrado.')
        panel.update(values)
    await store.mutate(guild_id, change)

async def create_panel(store, guild_id: int, title: str, description: str, color: int) -> dict:
    title, description = title.strip(), description.strip()
    if not 1 <= len(title) <= 256 or not 1 <= len(description) <= 4000:
        raise ValueError('Título ou descrição fora dos limites permitidos.')
    panel = {'id': secrets.token_hex(5), 'title': title, 'description': description,
             'color': color, 'channel_id': None, 'message_id': None,
             'created_at': datetime.now(timezone.utc).isoformat(), 'roles': {}, 'unique': False}
    def apply(data):
        panels = data.setdefault('panels', {})
        if len(panels) >= MAX_PANELS:
            raise ValueError(f'Limite de {MAX_PANELS} painéis por servidor.')
        while panel['id'] in panels:
            panel['id'] = secrets.token_hex(5)
        panels[panel['id']] = panel
    await store.mutate(guild_id, apply)
    return panel

async def save_publication(store, guild_id: int, panel_id: str, channel_id: int, message_id: int):
    def apply(data):
        panel = data.setdefault('panels', {}).get(panel_id)
        if panel is None:
            raise ValueError('Painel não encontrado.')
        panel['channel_id'] = str(channel_id)
        panel['message_id'] = str(message_id)
    await store.mutate(guild_id, apply)

async def delete_panel(store, guild_id: int, panel_id: str):
    def apply(data):
        if panel_id not in data.setdefault('panels', {}):
            raise ValueError('Painel não encontrado.')
        del data['panels'][panel_id]
    await store.mutate(guild_id, apply)
