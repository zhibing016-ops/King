"""Diagnóstico, exportação e restauração transacional de JSON por servidor."""
import json
from datetime import datetime, timezone
from .panels import MAX_PANELS

MAX_BACKUP_BYTES = 2_000_000
MAX_ROLES_PER_PANEL = 20


def validate_backup(raw: bytes, guild_id: int) -> dict:
    if not isinstance(raw, bytes) or len(raw) > MAX_BACKUP_BYTES or not raw:
        raise ValueError("Backup vazio ou maior que 2 MB.")
    try:
        data = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("O arquivo precisa ser um JSON UTF-8 válido.") from exc
    if not isinstance(data, dict) or data.get('guild_id') != str(guild_id):
        raise ValueError("O backup não pertence a este servidor.")
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ValueError("Versão de esquema incompatível.")
    if type(data.get('enabled')) is not bool:
        raise ValueError("Estado enabled inválido.")
    panels = data.get('panels')
    if not isinstance(panels, dict) or len(panels) > MAX_PANELS:
        raise ValueError("Quantidade de painéis inválida.")
    if not isinstance(data.get('settings'), dict):
        raise ValueError("Configurações do servidor inválidas.")
    for panel_id, panel in panels.items():
        if not isinstance(panel_id, str) or not isinstance(panel, dict) or panel.get('id') != panel_id:
            raise ValueError("Identificador de painel inconsistente.")
        if (not isinstance(panel.get('title'), str) or not 1 <= len(panel['title']) <= 256
                or not isinstance(panel.get('description'), str) or not 1 <= len(panel['description']) <= 4000
                or type(panel.get('color')) is not int or not 0 <= panel['color'] <= 0xffffff):
            raise ValueError(f"Aparência inválida no painel {panel_id}.")
        roles = panel.get('roles')
        if not isinstance(roles, dict) or len(roles) > MAX_ROLES_PER_PANEL:
            raise ValueError(f"Mapeamentos inválidos no painel {panel_id}.")
        for emoji, role_id in roles.items():
            if not isinstance(emoji, str) or not emoji or not str(role_id).isdecimal() or int(role_id) <= 0:
                raise ValueError(f"Cargo ou emoji inválido no painel {panel_id}.")
        if panel.get('interface', 'reactions') not in ('reactions', 'buttons', 'select'):
            raise ValueError(f"Interface inválida no painel {panel_id}.")
        for key in ('channel_id', 'message_id'):
            value = panel.get(key)
            if value is not None and (not str(value).isdecimal() or int(value) <= 0):
                raise ValueError(f"{key} inválido no painel {panel_id}.")
    return data


async def export_backup(store, guild_id: int) -> bytes:
    data = await store.get(guild_id)
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


async def restore_backup(store, guild_id: int, raw: bytes):
    restored = validate_backup(raw, guild_id)
    # Mutate under the store's per-guild lock, preserving atomic writes.
    def replace(data):
        data.clear()
        data.update(restored)
    await store.mutate(guild_id, replace)
    return len(restored['panels'])


def diagnose(data: dict, guild=None) -> list[tuple[str, str]]:
    issues = []
    if not isinstance(data, dict):
        return [('critical', 'Configuração não é um objeto JSON.')]
    if not isinstance(data.get('panels'), dict):
        return [('critical', 'Campo panels ausente ou inválido.')]
    if data.get('schema_version') != 1:
        issues.append(('critical', 'Versão do esquema diferente de 1.'))
    for panel_id, panel in data['panels'].items():
        if not isinstance(panel, dict):
            issues.append(('critical', f'Painel {panel_id}: estrutura inválida.'))
            continue
        label = str(panel.get('title', panel_id))[:60]
        if not panel.get('roles'):
            issues.append(('warning', f'{label}: nenhum cargo configurado.'))
        if not panel.get('channel_id') or not panel.get('message_id'):
            issues.append(('info', f'{label}: painel ainda não publicado.'))
        elif guild is not None and guild.get_channel(int(panel['channel_id'])) is None:
            issues.append(('warning', f'{label}: canal publicado não encontrado no cache.'))
        if guild is not None:
            for role_id in panel.get('roles', {}).values():
                role = guild.get_role(int(role_id)) if str(role_id).isdecimal() else None
                if role is None:
                    issues.append(('warning', f'{label}: cargo {role_id} não encontrado.'))
                elif guild.me and (role.managed or role >= guild.me.top_role):
                    issues.append(('warning', f'{label}: bot não pode gerenciar cargo {role_id}.'))
    if guild is not None and guild.me and not guild.me.guild_permissions.manage_roles:
        issues.append(('critical', 'O bot não possui Gerenciar Cargos.'))
    if not issues:
        issues.append(('ok', 'Nenhuma inconsistência detectada nas verificações locais.'))
    return issues
