"""WITEK Discord bot — main setup."""

import asyncio
import logging
from pathlib import Path

import discord

log = logging.getLogger(__name__)

_COG_DIR = Path(__file__).parent / "cogs"


def _ensure_event_loop():
    """Ensure an event loop exists in the current thread (Python 3.10+)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())


def create_bot(flask_app):
    """Create and configure the Discord bot.

    Parameters
    ----------
    flask_app : Flask
        The Flask application instance, stored on the bot so cogs can
        open ``app.app_context()`` for DB queries.
    """
    intents = discord.Intents.default()
    intents.guilds = True
    intents.guild_messages = True
    intents.message_content = True

    guild_id = flask_app.config.get("DISCORD_GUILD_ID")
    debug_guilds = [int(guild_id)] if guild_id else None

    _ensure_event_loop()

    bot = discord.Bot(intents=intents, debug_guilds=debug_guilds)
    bot.flask_app = flask_app

    # --- Events ---------------------------------------------------------- #

    @bot.event
    async def on_ready():
        log.info(
            "WITEK zalogowany jako %s (guilds: %d)", bot.user, len(bot.guilds)
        )
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="⚔️ WITEK | /thelp",
            )
        )

    @bot.event
    async def on_application_command_error(ctx, error):
        log.exception("Błąd komendy /%s: %s", ctx.command.name, error)
        await ctx.respond(
            "❌ Wystąpił błąd. Spróbuj ponownie później.", ephemeral=True
        )

    # --- Load cogs synchronously (py-cord load_extension is sync) -------- #

    for cog_file in sorted(_COG_DIR.glob("*.py")):
        if cog_file.name.startswith("_"):
            continue
        ext = f"bot.cogs.{cog_file.stem}"
        try:
            bot.load_extension(ext)
            log.info("Załadowano cog: %s", cog_file.stem)
        except Exception:
            log.exception("Nie udało się załadować cog: %s", ext)

    return bot


async def db_query(bot, fn):
    """Run a blocking DB function in an executor with Flask app context.

    Prevents blocking the Discord event loop for DB operations.

    Usage in cogs::

        result = await db_query(self.bot, lambda: Player.query.get(uid))
    """

    def _wrapped():
        with bot.flask_app.app_context():
            return fn()

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _wrapped)
