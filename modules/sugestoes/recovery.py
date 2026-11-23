"""Recuperação dos componentes persistentes de sugestões após reinício/restauração."""
import logging
from modules.sugestoes.config import DATA_DIR
from modules.sugestoes.storage import read_data

log = logging.getLogger(__name__)

async def register_vote_views(bot, guild_id=None):
    from modules.sugestoes.cogs.suggestions import VotacaoView
    if guild_id is None:
        ids = []
        for path in DATA_DIR.glob('guild_*.json'):
            try:
                ids.append(int(path.stem.removeprefix('guild_')))
            except ValueError:
                log.warning('Arquivo ignorado: %s', path.name)
    else:
        ids = [guild_id]
    total = 0
    for gid in ids:
        try:
            data = await read_data(gid)
            suggestions = data.get('suggestions', {})
            if not isinstance(suggestions, dict):
                raise ValueError('suggestions não é um objeto')
            for key, item in suggestions.items():
                if not isinstance(item, dict) or item.get('status') == 'Falha no envio':
                    continue
                message_id = item.get('message_id')
                if not message_id:
                    continue
                try:
                    number = int(key)
                    mid = int(message_id)
                    if number < 1 or mid < 1:
                        raise ValueError('IDs devem ser positivos')
                    bot.add_view(VotacaoView(gid, number), message_id=mid)
                    total += 1
                except (TypeError, ValueError) as exc:
                    log.warning('Sugestão %s em %s ignorada: %s', key, gid, exc)
        except (OSError, ValueError, TypeError) as exc:
            log.error('Não foi possível recuperar guild %s: %s', gid, exc)
    return total
