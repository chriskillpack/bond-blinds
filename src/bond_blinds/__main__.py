"""CLI entry point for bond-blinds."""

import argparse
import sys
import time

import httpx

from .config import Config, load_config

# How long to poll for the token after a bridge reboot
_TOKEN_POLL_TIMEOUT_SECONDS = 120
_TOKEN_POLL_INTERVAL_SECONDS = 3


def _find_bridge_host(cfg: Config) -> str:
    if cfg.bond.host:
        return cfg.bond.host
    from .discovery import DiscoveryError, discover_bridge

    if cfg.bond.name:
        print(f"Discovering Bond Bridge with name {cfg.bond.name!r}...")
    else:
        print("Discovering Bond Bridge on your network...")
    try:
        host = discover_bridge(name=cfg.bond.name)
        print(f"Found Bond Bridge at {host}")
        return host
    except DiscoveryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


def _retrieve_token_after_reboot(host: str) -> str:
    """Poll /v2/token until the bridge returns a token or we time out."""
    print()
    print("Please reboot your Bond Bridge now by unplugging and replugging the power.")
    print(
        f"Waiting up to {_TOKEN_POLL_TIMEOUT_SECONDS}s for the bridge to come back online..."
    )
    print()

    deadline = time.monotonic() + _TOKEN_POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"http://{host}/v2/token", timeout=5.0)
            if resp.status_code == 200:
                token = resp.json().get("token")
                if token:
                    return token
        except Exception:
            pass
        time.sleep(_TOKEN_POLL_INTERVAL_SECONDS)

    print(
        "error: timed out waiting for token. Try again or use the app method.",
        file=sys.stderr,
    )
    sys.exit(1)


def _token_setup_wizard(cfg: Config, config_path: str) -> None:
    print("=" * 60)
    print("Bond token not set in config.yaml")
    print("=" * 60)
    print()
    print("Option 1 — Bond Home App (no reboot needed):")
    print("  1. Open the Bond Home app on your phone")
    print("  2. Tap your Bond Bridge")
    print("  3. Go to Settings → Local Control API")
    print("  4. Copy the token shown")
    print(f"  5. Paste it into {config_path} as:")
    print("        bond:")
    print('          token: "your_token_here"')
    print()
    print("Option 2 — Auto-retrieve (requires a bridge reboot):")
    print("  We'll discover the bridge and fetch the token automatically")
    print("  from its setup endpoint immediately after reboot.")
    print()

    while True:
        choice = input("Choose an option (1 or 2), or q to quit: ").strip().lower()
        if choice == "q":
            sys.exit(0)
        elif choice == "1":
            print()
            print(f"Update bond.token in {config_path} and run again.")
            sys.exit(0)
        elif choice == "2":
            break
        else:
            print("Please enter 1, 2, or q.")

    host = _find_bridge_host(cfg)
    token = _retrieve_token_after_reboot(host)

    print(f"Token retrieved: {token}")
    print()
    print(f"Add this to {config_path}:")
    print("  bond:")
    print(f'    token: "{token}"')
    print()
    print("Then run the script again.")
    sys.exit(0)


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

    if not config.bond.token:
        _token_setup_wizard(config, args.config)

    from .daemon import run, send_command_now

    if args.open_now:
        send_command_now(config, "Open")
    elif args.close_now:
        send_command_now(config, "Close")
    else:
        run(config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
