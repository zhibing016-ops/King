"""Validação local sem conectar ao Discord. Execute: python check_project.py"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
systems = json.loads((ROOT / "config/systems.json").read_text(encoding="utf-8"))
routes = json.loads((ROOT / "config/interaction_routes.json").read_text(encoding="utf-8"))
settings = json.loads((ROOT / "data/settings.json").read_text(encoding="utf-8"))
assert isinstance(systems, dict) and systems, "Nenhum sistema cadastrado"
assert len(systems) <= 20, "Painel atual suporta no máximo 20 sistemas"
for key, info in systems.items():
    assert isinstance(info.get("enabled"), bool), f"enabled inválido: {key}"
    assert isinstance(info.get("name"), str) and info["name"], f"nome ausente: {key}"
    assert isinstance(info.get("emoji"), str), f"emoji ausente: {key}"
for kind in ("slash_commands", "component_prefixes"):
    for route, key in routes.get(kind, {}).items():
        assert route and key in systems, f"Rota inválida: {route} => {key}"
assert isinstance(settings, dict), "settings.json inválido"
print(f"OK: {len(systems)} sistemas, rotas e configurações JSON válidas")
