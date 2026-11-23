from modules.redeem.campaigns import active as campaign_active
"""Authorized HTTPS delivery adapter. One request per claim, with conservative retry semantics."""
import asyncio
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit
import aiohttp
from modules.redeem.api_probe import PublicResolver
from modules.redeem.availability import check as check_availability
from modules.redeem.api_config import normalize_url, validate_endpoint, secret_get

_LOCK = asyncio.Lock()

def now():
    return datetime.now(timezone.utc).isoformat()

def eligible(data, claim):
    game = data.get('games', {}).get(claim['game_key'])
    code = data.get('codes', {}).get(claim['code_id'])
    if not game or not code or str(game.get('guild_id')) != str(claim['guild_id']):
        raise ValueError('Jogo ou código indisponível.')
    if not campaign_active(data, code): raise ValueError('Campanha indisponível ou fora do período.')
    if not code.get('enabled', True): raise ValueError('Código desativado.')
    if code.get('expires_at') and datetime.fromisoformat(code['expires_at']) <= datetime.now(timezone.utc):
        raise ValueError('Código expirado.')
    if int(code.get('claims_count', 0)) >= int(code.get('max_claims', 1)):
        raise ValueError('Limite de resgates atingido.')
    # Exclude this already-reserved claim when checking availability at delivery.
    snapshot = dict(data)
    snapshot["claims"] = [c for c in data.get("claims", []) if c.get("id") != claim["id"]]
    check_availability(snapshot, code)
    api = game.get('api', {})
    if not api.get('enabled'): raise ValueError('Entrega desativada para este jogo.')
    base = normalize_url(api.get('base_url', ''))
    endpoint = validate_endpoint(api.get('claim_endpoint', ''), required=True)
    if urlsplit(base).path and endpoint.startswith('/'): raise ValueError('URL base deve ser somente domínio.')
    return game, code, api, base + endpoint

async def deliver_one(claim_id, guild_id):
    from modules.redeem.store import load, save
    async with _LOCK:
        data = load()
        claim = next((c for c in data['claims'] if c['id'] == claim_id and str(c['guild_id']) == str(guild_id)), None)
        if not claim: raise ValueError('Solicitação não encontrada.')
        if claim['status'] != 'pending': raise ValueError('Solicitação não está pendente. Confira o histórico antes de tentar novamente.')
        game, code, api, url = eligible(data, claim)
        token = secret_get(claim['game_key']) if api.get('auth_type', 'none') != 'none' else None
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json',
                   'User-Agent': 'KING-PLUS-Redeem/1', 'Idempotency-Key': claim['id']}
        if api.get('auth_type') == 'bearer':
            if not token: raise ValueError('Token não configurado.')
            headers['Authorization'] = 'Bearer ' + token
        elif api.get('auth_type') == 'api_key':
            if not token: raise ValueError('API Key não configurada.')
            headers['X-API-Key'] = token
        elif api.get('auth_type', 'none') != 'none': raise ValueError('Autenticação não suportada.')
        payload = {'claim_id': claim['id'], 'uid': claim['identifier'], 'server': claim['server'],
                   'code': code['code'], 'discord_user_id': str(claim['user_id']),
                   'rewards': code.get('reward_items', [code.get('reward', '')]),
                   'campaign_id': code.get('campaign_id')}
        claim['status'] = 'processing'
        claim['attempted_at'] = now()
        from modules.redeem.audit import append
        append(data, guild_id, 'delivery_started', claim_id=claim_id, details='Solicitação enviada para processamento')
        save(data)  # write BEFORE external side effect; never auto-retry unknown outcomes
        timeout = min(30, max(3, int(api.get('timeout', 15))))
        connector = aiohttp.TCPConnector(resolver=PublicResolver(), use_dns_cache=False, ssl=True)
        try:
            async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=timeout), trust_env=False) as session:
                async with session.post(url, headers=headers, json=payload, allow_redirects=False) as resp:
                    status = resp.status
                    body = await resp.content.read(8193)
                    if len(body) > 8192: raise ValueError('Resposta excede limite de segurança.')
                    parsed = json.loads(body) if body else {}
                    # Only explicit acknowledgement counts as delivered.
                    delivered = isinstance(parsed, dict) and parsed.get('delivered') is True
                    if 200 <= status < 300 and delivered:
                        claim['status'] = 'delivered'
                        claim['delivered_at'] = now()
                        claim['receipt'] = str(parsed.get('receipt_id', ''))[:120]
                        code['claims_count'] = int(code.get('claims_count', 0)) + 1
                        append(data, guild_id, 'delivery_confirmed', claim_id=claim_id, details='API confirmou entrega')
                        save(data)
                        return '✅ API confirmou entrega. Recibo: ' + (claim['receipt'] or 'não informado')
                    # Any other response could have had side effects; require manual reconciliation.
                    claim['status'] = 'review'
                    claim['http_status'] = status
                    append(data, guild_id, 'delivery_review', claim_id=claim_id, details=f'HTTP {status}; revisão manual necessária')
                    save(data)
                    return f'⚠️ Resposta HTTP {status} sem confirmação explícita de entrega. Revisão manual necessária; não reenvie automaticamente.'
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError, json.JSONDecodeError):
            claim['status'] = 'review'
            append(data, guild_id, 'delivery_review', claim_id=claim_id, details='Falha de rede ou resposta incerta; revisão manual')
            save(data)
            return '⚠️ Resultado incerto (rede/timeout/resposta). Verifique no jogo antes de qualquer nova tentativa.'
