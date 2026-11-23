"""Phase 10: inventory and UTC rolling-window availability checks."""
from datetime import datetime, timedelta, timezone

RESERVED = frozenset(('pending', 'processing', 'review'))

def policy(code):
    raw = code.get('availability', {})
    return {'stock': int(raw.get('stock', 0)), 'window_hours': int(raw.get('window_hours', 0)), 'window_limit': int(raw.get('window_limit', 0))}

def configure(code, stock, window_hours, window_limit, expiry):
    stock, window_hours, window_limit = int(stock), int(window_hours), int(window_limit)
    if not 0 <= stock <= 1000000 or not 0 <= window_hours <= 8760 or not 0 <= window_limit <= 1000000:
        raise ValueError('Estoque e limites: 0–1.000.000; janela: 0–8760 horas.')
    if bool(window_hours) != bool(window_limit):
        raise ValueError('Janela e limite devem ser ambos zero (desativados) ou ambos positivos.')
    expiry = expiry.strip()
    if expiry:
        try: dt = datetime.strptime(expiry, '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
        except ValueError: raise ValueError('Validade: AAAA-MM-DD HH:MM (UTC).')
        if dt <= datetime.now(timezone.utc): raise ValueError('A validade deve ser futura.')
        code['expires_at'] = dt.isoformat()
    else:
        code['expires_at'] = None
    code['availability'] = {'stock': stock, 'window_hours': window_hours, 'window_limit': window_limit}
    return code['availability']

def check(data, code):
    now = datetime.now(timezone.utc)
    expiry = code.get('expires_at')
    if expiry and datetime.fromisoformat(expiry) <= now: raise ValueError('Código expirado.')
    claims = [c for c in data.get('claims', []) if c.get('code_id') == code['id']]
    active = [c for c in claims if c.get('status') in RESERVED]
    delivered = int(code.get('claims_count', 0))
    if delivered + len(active) >= int(code.get('max_claims', 1)):
        raise ValueError('Limite global de resgates atingido ou reservado.')
    cfg = policy(code)
    if cfg['stock'] and delivered + len(active) >= cfg['stock']:
        raise ValueError('Estoque esgotado ou totalmente reservado.')
    if cfg['window_hours'] and cfg['window_limit']:
        cutoff = now - timedelta(hours=cfg['window_hours'])
        count = 0
        for claim in claims:
            if claim.get('status') not in RESERVED | {'delivered'}: continue
            try:
                created = datetime.fromisoformat(claim['created_at'])
                if created.tzinfo is None: created = created.replace(tzinfo=timezone.utc)
            except (KeyError, ValueError, TypeError): continue
            if created >= cutoff: count += 1
        if count >= cfg['window_limit']:
            raise ValueError('Limite de resgates da janela atual atingido.')
