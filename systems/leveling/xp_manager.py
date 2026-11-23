"""Regras de elegibilidade e prevenção simples de farm de XP."""
import random
import time
from collections import OrderedDict

class XPManager:
    def __init__(self):
        self.recent = OrderedDict()

    def eligible(self, message, config):
        if not config.get("enabled", False) or message.guild is None or message.author.bot:
            return False
        if message.channel.id in config.get("ignored_channel_ids", []):
            return False
        if any(role.id in config.get("ignored_role_ids", []) for role in getattr(message.author, "roles", [])):
            return False
        content = " ".join(message.content.casefold().split())
        if len(content) < 3:
            return False
        key = (message.guild.id, message.author.id)
        now = time.monotonic()
        previous = self.recent.get(key)
        if previous and now - previous[0] < config["cooldown_seconds"]:
            return False
        if previous and content == previous[1] and now - previous[0] < 300:
            return False
        self.recent[key] = (now, content)
        self.recent.move_to_end(key)
        while len(self.recent) > 100000:
            self.recent.popitem(last=False)
        return True

    @staticmethod
    def amount(config):
        return random.randint(config["xp_per_message_min"], config["xp_per_message_max"])
