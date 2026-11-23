"""Formatação segura dos anúncios de subida de nível."""
import re

DEFAULT_MESSAGE = "🎉 Parabéns {mention}! Você alcançou o nível **{level}**!"
ALLOWED = {"mention", "member", "level", "previous_level", "guild"}
TOKEN = re.compile(r"\{([^{}]+)\}")

def validate_template(template: str) -> str:
    if not isinstance(template, str) or not (1 <= len(template) <= 1000):
        raise ValueError("A mensagem deve conter de 1 a 1000 caracteres.")
    tokens = TOKEN.findall(template)
    if any(token not in ALLOWED for token in tokens) or template.count("{") != len(tokens) or template.count("}") != len(tokens):
        raise ValueError("Use apenas {mention}, {member}, {level}, {previous_level} e {guild}.")
    return template

def render_announcement(template: str, *, member_name: str, member_id: int, level: int, previous_level: int, guild_name: str) -> str:
    template = validate_template(template)
    values = {"mention": f"<@{member_id}>", "member": member_name, "level": str(level), "previous_level": str(previous_level), "guild": guild_name}
    return TOKEN.sub(lambda match: values[match.group(1)], template)
