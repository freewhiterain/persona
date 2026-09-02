"""persona CLI.

    persona init  [--character lin]        create the DB, seed a character
    persona chat  [--character lin] [--user 我]
                                          talk in the terminal (daemon runs in-process)
    persona run   [--character lin]        daemon only (for external connectors)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from persona.config import get_settings
from persona.logging_conf import get_logger, setup_logging

logger = get_logger(__name__)


def _cmd_init(args: argparse.Namespace) -> int:
    from persona.chat.cards import seed_character
    from persona.store.db import get_db

    get_db().init_schema()
    row = seed_character(args.character)
    s = get_settings()
    print(f"db:        {s.db_path}")
    print(f"character: {row['display_name']} ({row['id']})")
    print(f"preset:    {s.cfg.prompt_preset}   embedder: {s.effective_embedder}   fake_llm: {s.fake_llm}")
    print("ready. run:  uv run persona chat")
    return 0


async def _chat(character_alias: str, user_name: str) -> None:
    from persona.connectors.terminal import TerminalConnector
    from persona.chat.cards import seed_character
    from persona.runner.daemon import run_daemon
    from persona.store.db import get_db
    from persona.store.users import UserStore

    get_db().init_schema()
    seed_character(character_alias)
    users = UserStore()
    character = users.get_by_name(character_alias)
    user = users.upsert(name=user_name, display_name=user_name)

    conn = TerminalConnector(
        user_id=user["id"], user_name=user_name,
        character_id=character["id"], character_name=character["display_name"],
    )
    tasks = [
        asyncio.create_task(run_daemon(character["id"])),
        asyncio.create_task(conn.run_inbound()),
        asyncio.create_task(conn.run_outbound()),
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            t.cancel()


def _cmd_chat(args: argparse.Namespace) -> int:
    # keep the REPL readable; override with PERSONA_LOG_LEVEL
    if "PERSONA_LOG_LEVEL" not in os.environ:
        logging.getLogger("persona").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(_chat(args.character, args.user))
    except (KeyboardInterrupt, EOFError):
        print("\n再见。")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from persona.chat.cards import seed_character
    from persona.runner.daemon import run_daemon
    from persona.store.db import get_db
    from persona.store.users import UserStore

    get_db().init_schema()
    seed_character(args.character)
    character = UserStore().get_by_name(args.character)
    try:
        asyncio.run(run_daemon(character["id"]))
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="persona", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="create the DB and seed a character")
    pi.add_argument("--character", default="lin")
    pi.set_defaults(func=_cmd_init)

    pc = sub.add_parser("chat", help="talk in the terminal")
    pc.add_argument("--character", default="lin")
    pc.add_argument("--user", default="我")
    pc.set_defaults(func=_cmd_chat)

    pr = sub.add_parser("run", help="run the daemon only")
    pr.add_argument("--character", default="lin")
    pr.set_defaults(func=_cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
