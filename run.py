"""W.I.T.E.K — Entrypoint.

Usage:
    python run.py                 # Start Flask web server
    python run.py --collect       # Fetch map.sql and store snapshot
    python run.py --scheduled     # Start Flask + interval collection (every N min)
    python run.py --bot-only      # Run only the Discord bot (no Flask)
"""

import argparse
import asyncio
import logging
import os
import signal
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

log = logging.getLogger(__name__)

from app import create_app
from app.map_sql.collector import collect_and_store


# ------------------------------------------------------------------ #
# Discord bot runner (executed in a separate thread)
# ------------------------------------------------------------------ #

def _run_bot_thread(flask_app, token):
    """Start the Discord bot in its own asyncio event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    from bot.bot import create_bot

    bot = create_bot(flask_app)

    try:
        loop.run_until_complete(bot.start(token))
    except (KeyboardInterrupt, asyncio.CancelledError):
        loop.run_until_complete(bot.close())
    finally:
        loop.close()


def _start_bot(flask_app):
    """Launch the Discord bot in a daemon thread.

    Returns the thread, or None if no DISCORD_TOKEN is configured.
    Guards against Flask debug-mode reloader spawning duplicate bots.
    """
    token = flask_app.config.get("DISCORD_TOKEN")
    if not token:
        log.warning("DISCORD_TOKEN nie ustawiony — bot Discord nie wystartuje")
        return None

    # Flask reloader forks a child process. Only start the bot in the
    # child (WERKZEUG_RUN_MAIN == "true") or when the reloader is off.
    if flask_app.config.get("DEBUG") and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return None

    thread = threading.Thread(
        target=_run_bot_thread,
        args=(flask_app, token),
        daemon=True,
        name="discord-bot",
    )
    thread.start()
    log.info("Bot Discord uruchomiony w tle (thread: %s)", thread.name)
    return thread


def main():
    parser = argparse.ArgumentParser(description="W.I.T.E.K — Travian Alliance Tool")
    parser.add_argument(
        "--collect", action="store_true", help="Fetch map.sql and store snapshot now"
    )
    parser.add_argument(
        "--from-file", type=str, help="Import map.sql from local file instead of fetching"
    )
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="Start Flask with scheduled map.sql collection (interval)",
    )
    parser.add_argument(
        "--bot-only",
        action="store_true",
        help="Run only the Discord bot (no Flask web server)",
    )
    parser.add_argument("--port", type=int, default=5000, help="Flask port")
    args = parser.parse_args()

    app = create_app()

    # -- One-shot commands ------------------------------------------------ #

    if args.collect:
        print("🗺️  Pobieranie map.sql...")
        snapshot = collect_and_store(app)
        if snapshot:
            print(f"✅ Snapshot #{snapshot.id}: {snapshot.village_count} wiosek")
        else:
            print("❌ Nie udało się pobrać danych")
        return

    if args.from_file:
        from app.map_sql.collector import store_snapshot

        print(f"📂 Importuję z pliku: {args.from_file}")
        with open(args.from_file, "r", encoding="utf-8") as f:
            raw = f.read()
        with app.app_context():
            snapshot = store_snapshot(raw)
        print(f"✅ Snapshot #{snapshot.id}: {snapshot.village_count} wiosek")
        return

    # -- Bot-only mode ---------------------------------------------------- #

    if args.bot_only:
        token = app.config.get("DISCORD_TOKEN")
        if not token:
            print("❌ DISCORD_TOKEN nie ustawiony w .env")
            return

        print("🤖 W.I.T.E.K — tryb bot-only (Ctrl+C aby zatrzymać)")

        from bot.bot import create_bot

        bot = create_bot(app)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def _shutdown(sig, frame):
            log.info("Zamykanie bota...")
            loop.call_soon_threadsafe(loop.stop)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        try:
            loop.run_until_complete(bot.start(token))
        except (KeyboardInterrupt, SystemExit):
            loop.run_until_complete(bot.close())
        finally:
            loop.close()
        return

    # -- Scheduled collection --------------------------------------------- #

    if args.scheduled:
        from apscheduler.schedulers.background import BackgroundScheduler
        from datetime import datetime, timezone

        interval_min = app.config["FETCH_INTERVAL_MINUTES"]

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            collect_and_store,
            "interval",
            args=[app],
            minutes=interval_min,
            id="map_sql_interval",
        )
        scheduler.start()
        log.info(
            "Scheduler uruchomiony: map.sql co %d min",
            interval_min,
        )

        # Log startup configuration summary
        log.info("--- Konfiguracja startu ---")
        log.info("  Travian URL: %s", app.config.get("TRAVIAN_SERVER_URL"))
        log.info("  Nasze sojusze: %s", app.config.get("TRAVIAN_OUR_ALLIANCES"))
        log.info("  Interwał zbierania: %d min", interval_min)
        log.info("  Próg spadku pop: %d%%", app.config.get("POP_DROP_THRESHOLD", 15))
        log.info("  Promień nowych wiosek: %d pól", app.config.get("NEW_VILLAGE_RADIUS", 30))
        log.info("  Kanał alertów: %s", app.config.get("DISCORD_ALERTS_CHANNEL_ID"))
        log.info("  Discord Guild: %s", app.config.get("DISCORD_GUILD_ID"))
        log.info("  OAuth redirect: %s", app.config.get("DISCORD_REDIRECT_URI"))
        log.info("  Extension API: %s", "TAK" if app.config.get("EXT_API_TOKEN") else "NIE")
        log.info("---------------------------")

        # Fetch on startup if no recent snapshot exists
        with app.app_context():
            from app.models import Snapshot

            latest = Snapshot.query.order_by(Snapshot.fetched_at.desc()).first()
            if latest is None:
                print("Brak snapshotow - pobieram map.sql na starcie...")
                collect_and_store(app)
            else:
                now = datetime.now(timezone.utc)
                fetched = latest.fetched_at
                # SQLite stores naive datetimes — treat as UTC
                if fetched.tzinfo is None:
                    fetched = fetched.replace(tzinfo=timezone.utc)
                age_min = (now - fetched).total_seconds() / 60
                if age_min > interval_min:
                    print(
                        f"Ostatni snapshot sprzed {int(age_min)} min - pobieram aktualne dane..."
                    )
                    collect_and_store(app)

    # -- Start Discord bot in background thread --------------------------- #

    _start_bot(app)

    # -- Start Flask ------------------------------------------------------ #

    print(f"W.I.T.E.K startuje na http://localhost:{args.port}")
    app.run(host="0.0.0.0", port=args.port, debug=app.config["DEBUG"])


if __name__ == "__main__":
    main()
