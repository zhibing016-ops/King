"""Safe, read-only API health checks. Never calls the claim endpoint."""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit
import aiohttp
from aiohttp.abc import AbstractResolver
from .api_config import normalize_url, validate_endpoint, secret_get

class PublicResolver(AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        output = []
        for af, _, _, _, address in records:
            ip = ipaddress.ip_address(address[0])
            if not ip.is_global:
                raise ValueError('DNS aponta para endereço não público; conexão bloqueada.')
            output.append({'hostname': host, 'host': str(ip), 'port': port, 'family': af, 'proto': 0, 'flags': 0})
        if not output: raise ValueError('DNS não retornou endereços.')
        return output
    async def close(self): pass

async def check_api(api, game_key):
    base = normalize_url(api.get('base_url', ''))
    health = validate_endpoint(api.get('health_endpoint', ''), required=False)
    if not health:
        return '⚠️ Configure um endpoint de status (GET) antes de testar. O endpoint Claim nunca é chamado pelo diagnóstico.'
    if not health.startswith('/') or health == api.get('claim_endpoint'):
        return '⛔ O endpoint de status deve ser diferente do endpoint Claim.'
    timeout = min(30, max(3, int(api.get('timeout', 15))))
    auth = api.get('auth_type', 'none')
    headers = {'Accept': 'application/json', 'User-Agent': 'KING-PLUS-Redeem-Health/1'}
    if auth != 'none':
        secret = secret_get(game_key)
        if not secret: return '⚠️ Credencial não configurada.'
        if auth == 'bearer': headers['Authorization'] = 'Bearer ' + secret
        elif auth == 'api_key': headers['X-API-Key'] = secret
        else: return '⚠️ Método de autenticação não suportado.'
    # DNS resolution is checked on every connection, and pinned to vetted IPs.
    connector = aiohttp.TCPConnector(resolver=PublicResolver(), use_dns_cache=False, ssl=True)
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=timeout), trust_env=False) as session:
            async with session.get(base + health, headers=headers, allow_redirects=False) as response:
                status = response.status
                if 200 <= status < 300: return f'✅ API respondeu HTTP {status}. Endpoint de status acessível; isso não garante que Claim ou correio in-game funcionem.'
                if status in (401, 403): return f'🔐 HTTP {status}: acesso negado. Confira credenciais e permissões.'
                if 300 <= status < 400: return f'⚠️ HTTP {status}: redirecionamento bloqueado por segurança.'
                return f'⚠️ HTTP {status}: endpoint respondeu, mas não confirmou saúde.'
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as exc:
        return f'❌ Falha no diagnóstico ({type(exc).__name__}). Confira URL, DNS, TLS e disponibilidade.'
