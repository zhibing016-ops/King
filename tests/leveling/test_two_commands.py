"""Validação estrutural sem conexão ao Discord."""
import ast
from pathlib import Path


def test_exactly_two_slash_commands():
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / 'systems/leveling/cog.py').read_text(encoding='utf-8'))
    registered = []
    for cls in tree.body:
        if isinstance(cls, ast.ClassDef) and cls.name == 'Leveling':
            for node in cls.body:
                if isinstance(node, ast.AsyncFunctionDef):
                    for dec in node.decorator_list:
                        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == 'command':
                            for kw in dec.keywords:
                                if kw.arg == 'name' and isinstance(kw.value, ast.Constant):
                                    registered.append(kw.value.value)
    assert sorted(registered) == ['nivel', 'perfil']
