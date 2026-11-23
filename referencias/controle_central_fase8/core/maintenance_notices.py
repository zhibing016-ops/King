"""Avisos públicos de alteração de estado dos módulos."""
import json
import os
from pathlib import Path
import discord

SETTINGS = Path(__file__).resolve().parent.parent / 'data' / 'settings.json'


def notice_channel_id():
    try:
        return (json.loads(SETTINGS.read_text(encoding='utf-8'))).get('notice_channel_id')
    except (OSError, ValueError):
        return None


def save_notice_channel(channel_id):
    data = json.loads(SETTINGS.read_text(encoding='utf-8')) if SETTINGS.exists() else {}
    data['notice_channel_id'] = channel_id
    tmp = SETTINGS.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, SETTINGS)


async def send_maintenance_notice(bot, key, enabled, actor):
    """Retorna (sucesso, detalhe); não desfaz a alteração se o envio falhar."""
    channel_id = notice_channel_id()
    if not channel_id:
        return False, 'Canal de avisos não configurado. Use /canal_avisos.'
    try:
        channel = bot.get_channel(int(channel_id)) or await bot.fetch_channel(int(channel_id))
        if not hasattr(channel, 'send'):
            return False, 'O canal configurado não aceita mensagens.'
        system = bot.system_manager.systems[key]
        if enabled:
            embed = discord.Embed(title='✅ Manutenção concluída', description=f"{system['emoji']} **{system['name']}** foi ativado com sucesso.\nOs serviços estão disponíveis novamente.", color=discord.Color.green())
        else:
            embed = discord.Embed(title='🔧 Sistema em manutenção', description=f"{system['emoji']} **{system['name']}** foi desativado temporariamente para manutenção.\nAguarde a normalização dos serviços.", color=discord.Color.orange())
        embed.set_footer(text='KING PLUS • Controle Central de Sistemas')
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        return True, 'Aviso publicado.'
    except (discord.Forbidden, discord.NotFound, discord.HTTPException, ValueError, TypeError) as exc:
        return False, f'Não foi possível publicar o aviso ({type(exc).__name__}). Confira permissões e canal.'


def get_setting(key):
    try:
        return json.loads(SETTINGS.read_text(encoding='utf-8')).get(key)
    except (OSError, ValueError):
        return None

def save_setting(key, value):
    data = json.loads(SETTINGS.read_text(encoding='utf-8')) if SETTINGS.exists() else {}
    data[key] = value
    tmp = SETTINGS.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, SETTINGS)
