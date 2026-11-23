"""Entrada única: carrega o token e inicia o bot."""
import asyncio
import logging
import os
from dotenv import load_dotenv
from bot import KingPlus

async def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    token = (os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("Configure DISCORD_TOKEN no .env")
    async with KingPlus() as bot:
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
