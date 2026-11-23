"""Modo Verify: reação concede cargo permanente até ação administrativa."""

def is_verify(panel: dict) -> bool:
    return bool(panel.get('verify', False))


def validate_verify_panel(panel: dict) -> None:
    if len(panel.get('roles', {})) != 1:
        raise ValueError('Modo Verify exige exatamente uma associação emoji/cargo no painel.')


async def set_verify(store, guild_id: int, panel_id: str, enabled: bool) -> dict:
    def change(data):
        panel = data.setdefault('panels', {}).get(panel_id)
        if panel is None:
            raise ValueError('Painel não encontrado.')
        if enabled:
            validate_verify_panel(panel)
            if panel.get('unique') or panel.get('reversed') or panel.get('binding'):
                raise ValueError('Desative Unique, Reversed ou Binding antes de ativar Verify.')
        panel['verify'] = bool(enabled)
    data = await store.mutate(guild_id, change)
    return data['panels'][panel_id]
