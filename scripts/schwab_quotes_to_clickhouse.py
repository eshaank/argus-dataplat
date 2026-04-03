#!/usr/bin/env python3
"""
Minimal test: Schwab Market Data GET /quotes → local ClickHouse.

Schwab uses OAuth 2.0. App Key + Secret alone cannot call the API; you need tokens
from a one-time browser login (`oauth` subcommand), then `sync` refreshes and fetches.

Quote API shape: see argus-dataplat/QUOTE.md (GET /quotes, symbols query param).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import sys
import threading
import time
import urllib.parse
import uuid
import warnings
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import clickhouse_connect
import httpx
from dotenv import load_dotenv

TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
QUOTES_URL = "https://api.schwabapi.com/marketdata/v1/quotes"


def _utc_now_ms() -> datetime:
    return datetime.now(timezone.utc)


def load_env() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _unwrap_token_file(raw: dict) -> tuple[dict, int | None]:
    """Support both schwab-py style {creation_timestamp, token: {...}} and flat OAuth JSON."""
    if "token" in raw and isinstance(raw["token"], dict):
        return raw["token"], raw.get("creation_timestamp")
    return raw, raw.get("creation_timestamp")


def load_token(path: Path) -> dict:
    with path.open() as f:
        raw = json.load(f)
    token, _ = _unwrap_token_file(raw)
    return token


def save_token(path: Path, token: dict, creation_ts: int | None = None) -> None:
    if creation_ts is None:
        creation_ts = int(_utc_now_ms().timestamp())
    wrapper = {"creation_timestamp": creation_ts, "token": token}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(wrapper, indent=2))


def exchange_authorization_code(
    app_key: str, app_secret: str, code: str, redirect_uri: str
) -> dict:
    r = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": app_key,
        },
        auth=(app_key, app_secret),
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()


def refresh_tokens(app_key: str, app_secret: str, refresh_token: str) -> dict:
    r = httpx.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(app_key, app_secret),
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()


def _exchange_code_from_callback_url(
    pasted: str,
    state: str,
    app_key: str,
    app_secret: str,
    redirect_uri: str,
    token_path: Path,
) -> None:
    parsed = urllib.parse.urlparse(pasted)
    params = urllib.parse.parse_qs(parsed.query)
    err = params.get("error", [None])[0]
    if err:
        desc = params.get("error_description", [""])[0]
        print(f"Schwab returned OAuth error: {err} {desc}", file=sys.stderr)
        sys.exit(1)
    if params.get("state", [None])[0] != state:
        print("Warning: state mismatch; continuing if code is present.", file=sys.stderr)
    codes = params.get("code")
    if not codes:
        print("No ?code= in URL. Check redirect and app callback settings.", file=sys.stderr)
        sys.exit(1)
    code = urllib.parse.unquote(codes[0])
    token = exchange_authorization_code(app_key, app_secret, code, redirect_uri)
    save_token(token_path, token)
    print(f"Saved tokens to {token_path}")


def _build_authorize_url(app_key: str, redirect_uri: str, state: str) -> str:
    q = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": app_key,
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return f"{AUTH_URL}?{q}"


def cmd_oauth(
    app_key: str, app_secret: str, redirect_uri: str, token_path: Path, serve_callback: bool
) -> None:
    state = str(uuid.uuid4())
    url = _build_authorize_url(app_key, redirect_uri, state)

    if serve_callback:
        cmd_oauth_with_local_server(
            app_key, app_secret, redirect_uri, token_path, state, url
        )
        return

    print(
        """
What you should see
-------------------
1) Opening the URL below sends you to Schwab's LOGIN page (schwab.com-style),
   NOT the developer.schwab.com portal. Use your normal brokerage login
   (Client ID + password), same as schwab.com.

2) After you approve the app, the browser is sent to your Callback URL with
   ?code=...&session=... in the address bar. For https://127.0.0.1 with no
   local server, the page often shows "can't connect" / ERR_CONNECTION_REFUSED.
   That is OK — copy the ENTIRE URL from the address bar anyway (it still
   contains the code).

3) SCHWAB_REDIRECT_URI in .env must match the Callback URL in the Schwab
   developer app EXACTLY (https vs http, port, path, trailing slash).

If you LOG IN successfully but land on the LOGIN PAGE AGAIN (loop): try Chrome
(not Safari), turn off strict tracking prevention for the test, clear cookies
for schwab.com, and ensure the authorize URL's redirect_uri matches your app.
Best fix: use oauth --serve-callback with SCHWAB_REDIRECT_URI=https://127.0.0.1:8182
(register that exact URL in the developer portal; may require app re-approval).

If you see an error on Schwab's site BEFORE the login form (e.g. invalid
client, redirect_uri mismatch), fix the app Callback URL and .env, then retry.

If the URL you paste has ?error= in it, paste that full URL; the script will
report the OAuth error from Schwab.
"""
    )
    print("Open this URL in a browser:\n")
    print(url)
    print("\nPaste the FULL URL from the address bar after Schwab redirects you:\n")
    pasted = input("Callback URL: ").strip()
    _exchange_code_from_callback_url(
        pasted, state, app_key, app_secret, redirect_uri, token_path
    )


def cmd_oauth_with_local_server(
    app_key: str,
    app_secret: str,
    redirect_uri: str,
    token_path: Path,
    state: str,
    auth_url: str,
) -> None:
    try:
        from flask import Flask, request
    except ImportError:
        print(
            "Flask is required for --serve-callback. Run:\n"
            "  uv sync --group oauth-server\n"
            "Then retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.hostname != "127.0.0.1":
        print("--serve-callback only supports callback host 127.0.0.1", file=sys.stderr)
        sys.exit(1)
    port = parsed.port
    if port is None or port == 443:
        print(
            "Use an explicit high port in SCHWAB_REDIRECT_URI, e.g. "
            "https://127.0.0.1:8182 (must match the developer portal exactly).",
            file=sys.stderr,
        )
        sys.exit(1)
    callback_path = parsed.path if parsed.path else "/"

    result_q: queue.Queue[str] = queue.Queue()
    flask_app = Flask(__name__)

    @flask_app.route(callback_path)
    def handle_oauth_redirect() -> str:
        result_q.put(request.url)
        return (
            "<html><body><p>OAuth callback received. You can close this tab.</p></body></html>"
        )

    status_path = "/schwab-oauth-local/status"

    @flask_app.route(status_path)
    def status() -> str:
        return "ok"

    def run_flask() -> None:
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)
        flask_app.run(
            host="127.0.0.1",
            port=port,
            ssl_context="adhoc",
            use_reloader=False,
            threaded=True,
        )

    thread = threading.Thread(target=run_flask, daemon=True)
    thread.start()

    status_url = f"https://127.0.0.1:{port}{status_path}"
    ready = False
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for _ in range(150):
            try:
                httpx.get(status_url, verify=False, timeout=1.0)
                ready = True
                break
            except Exception:
                time.sleep(0.1)

    if not ready:
        print("Local HTTPS callback server did not start; check the port is free.", file=sys.stderr)
        sys.exit(1)

    print(
        """
Local HTTPS callback server is running on your machine (self-signed cert).

1) Register this EXACT callback in the Schwab developer app and .env:
"""
        f"     {redirect_uri}\n"
        """
2) Your browser will warn about the certificate when Schwab redirects back —
   that is expected; proceed to localhost (same approach as schwab-py).

3) Use Chrome if Safari loops at login.

Press Enter to open the Schwab authorize page...
"""
    )
    input()
    webbrowser.open(auth_url)

    try:
        pasted = result_q.get(timeout=300.0)
    except queue.Empty:
        print("Timed out waiting for redirect to callback URL.", file=sys.stderr)
        sys.exit(1)

    _exchange_code_from_callback_url(
        pasted, state, app_key, app_secret, redirect_uri, token_path
    )


def ensure_access_token(
    app_key: str, app_secret: str, token_path: Path
) -> str:
    if not token_path.is_file():
        print(
            f"Missing {token_path}. Run: uv run python scripts/schwab_quotes_to_clickhouse.py oauth",
            file=sys.stderr,
        )
        sys.exit(1)
    token = load_token(token_path)
    access = token.get("access_token")
    refresh = token.get("refresh_token")
    if not refresh:
        print("Token file has no refresh_token; run oauth again.", file=sys.stderr)
        sys.exit(1)
    # Cheap approach: always refresh so we do not parse expires_in.
    new_t = refresh_tokens(app_key, app_secret, refresh)
    # Preserve creation_timestamp from original file when refreshing
    with token_path.open() as f:
        raw = json.load(f)
    _, creation_ts = _unwrap_token_file(raw)
    if creation_ts is None:
        creation_ts = int(_utc_now_ms().timestamp())
    save_token(token_path, new_t, creation_ts=creation_ts)
    return new_t["access_token"]


def fetch_quotes(access_token: str, symbols: str) -> dict:
    correl = str(uuid.uuid4())
    r = httpx.get(
        QUOTES_URL,
        params={"symbols": symbols},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Schwab-Client-CorrelId": correl,
            "Schwab-Resource-Version": "1",
        },
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()


def ensure_table(ch) -> None:
    ch.command(
        """
        CREATE TABLE IF NOT EXISTS schwab_quotes
        (
            symbol LowCardinality(String),
            fetched_at DateTime64(3, 'UTC'),
            data String CODEC(ZSTD(3))
        )
        ENGINE = MergeTree
        ORDER BY (symbol, fetched_at)
        """
    )


def cmd_sync(
    app_key: str,
    app_secret: str,
    token_path: Path,
    symbols: str,
    ch_host: str,
    ch_port: int,
    ch_user: str,
    ch_password: str,
    ch_database: str,
) -> None:
    access = ensure_access_token(app_key, app_secret, token_path)
    body = fetch_quotes(access, symbols)
    if not isinstance(body, dict):
        print("Unexpected response (not a JSON object).", file=sys.stderr)
        sys.exit(1)

    fetched = _utc_now_ms()
    rows: list[tuple[str, datetime, str]] = []
    for symbol, payload in body.items():
        rows.append((symbol, fetched, json.dumps(payload)))

    ch = clickhouse_connect.get_client(
        host=ch_host,
        port=ch_port,
        username=ch_user,
        password=ch_password or "",
        database=ch_database,
    )
    ensure_table(ch)
    if rows:
        ch.insert("schwab_quotes", rows, column_names=["symbol", "fetched_at", "data"])
    print(f"Inserted {len(rows)} row(s) into {ch_database}.schwab_quotes")


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Schwab quotes → ClickHouse (minimal test)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_oauth = sub.add_parser("oauth", help="Browser login; saves tokens to SCHWAB_TOKEN_PATH")
    p_oauth.add_argument(
        "--serve-callback",
        action="store_true",
        help=(
            "Start local HTTPS server on redirect port (use with "
            "https://127.0.0.1:HIGHPORT matching the portal). "
            "Requires: uv sync --group oauth-server"
        ),
    )
    p_sync = sub.add_parser("sync", help="Refresh token, GET /quotes, insert into ClickHouse")

    args = parser.parse_args()

    app_key = os.environ.get("SCHWAB_APP_KEY", "").strip()
    app_secret = os.environ.get("SCHWAB_APP_SECRET", "").strip()
    redirect_uri = os.environ.get("SCHWAB_REDIRECT_URI", "https://127.0.0.1").strip()
    token_path = Path(os.environ.get("SCHWAB_TOKEN_PATH", ".schwab_token.json")).resolve()

    if args.cmd == "oauth":
        if not app_key or not app_secret:
            print("Set SCHWAB_APP_KEY and SCHWAB_APP_SECRET in .env", file=sys.stderr)
            sys.exit(1)
        cmd_oauth(
            app_key,
            app_secret,
            redirect_uri,
            token_path,
            serve_callback=getattr(args, "serve_callback", False),
        )
        return

    symbols = os.environ.get("SCHWAB_SYMBOLS", "AAPL,MSFT").strip()
    ch_host = os.environ.get("CLICKHOUSE_HOST", "localhost")
    ch_port = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
    ch_user = os.environ.get("CLICKHOUSE_USER", "default")
    ch_password = os.environ.get("CLICKHOUSE_PASSWORD", "")
    ch_database = os.environ.get("CLICKHOUSE_DATABASE", "default")

    if not app_key or not app_secret:
        print("Set SCHWAB_APP_KEY and SCHWAB_APP_SECRET in .env", file=sys.stderr)
        sys.exit(1)

    cmd_sync(
        app_key,
        app_secret,
        token_path,
        symbols,
        ch_host,
        ch_port,
        ch_user,
        ch_password,
        ch_database,
    )


if __name__ == "__main__":
    main()
