"""CLI entry point for bond-blinds."""

import argparse
import sys

from .config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="bond-blinds",
        description="Schedule RF blind commands via Bond Bridge with retry support.",
    )
    parser.add_argument(
        "--config",
        required=True,
        metavar="CONFIG",
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate and log schedule without sending commands",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--open-now",
        action="store_true",
        help="Send Open to all devices immediately and exit",
    )
    group.add_argument(
        "--close-now",
        action="store_true",
        help="Send Close to all devices immediately and exit",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"error: config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    from .daemon import run, send_command_now

    if args.open_now:
        send_command_now(config, "Open")
    elif args.close_now:
        send_command_now(config, "Close")
    else:
        run(config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
