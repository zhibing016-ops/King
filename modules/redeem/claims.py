from modules.redeem.campaigns import active as campaign_active
"""Phase 06: request intake only; no API call or reward delivery."""
from datetime import datetime, timezone
from uuid import uuid4
from datetime import timedelta
from modules.redeem.limits import enforce_limits
from modules.redeem.availability import check as check_availability
from modules.redeem.codes import normalize_code
from modules.redeem.validation import validate_player


def submit_claim(data, guild_id, game_key, user_id, identifier, server, code):
    games = data.get('games', {})
    game = games.get(game_key)
    if not game or str(game.get('guild_id')) != str(guild_id):
        raise ValueError('Jogo não encontrado neste servidor.')
    identifier, server = validate_player(game, identifier, server)
    normalized = normalize_code(code)
    record = next((r for r in data.get('codes', {}).values()
        if str(r.get('guild_id')) == str(guild_id) and r.get('game_key') == game_key
        and r.get('code') == normalized), None)
    if not record:
        raise ValueError('Código inválido para este jogo.')
    if not campaign_active(data, record):
        raise ValueError('Campanha indisponível ou fora do período.')
    if not record.get('enabled', True):
        raise ValueError('Código desativado.')
    expiry = record.get('expires_at')
    if expiry and datetime.fromisoformat(expiry) <= datetime.now(timezone.utc):
        raise ValueError('Código expirado.')
    if int(record.get('claims_count', 0)) >= int(record.get('max_claims', 1)):
        raise ValueError('Código esgotado.')
    claims = data.setdefault('claims', [])
    enforce_limits(data, guild_id, game_key, record, user_id, identifier)
    check_availability(data, record)
    reserved = sum(1 for c in claims if c.get('code_id') == record['id'] and str(c.get('guild_id')) == str(guild_id) and c.get('status') in ('pending', 'processing', 'review'))
    if int(record.get('claims_count', 0)) + reserved >= int(record.get('max_claims', 1)):
        raise ValueError('Todas as vagas deste código estão entregues ou reservadas.')
    claim = {'id': uuid4().hex, 'guild_id': guild_id, 'game_key': game_key,
             'code_id': record['id'], 'user_id': user_id, 'identifier': identifier,
             'server': server, 'status': 'pending', 'created_at': datetime.now(timezone.utc).isoformat()}
    claims.append(claim)
    from modules.redeem.audit import append
    append(data, guild_id, "claim_created", claim_id=claim["id"], actor_id=user_id, details="Solicitação pendente registrada")
    return claim
