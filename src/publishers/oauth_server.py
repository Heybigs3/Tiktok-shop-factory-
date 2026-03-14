"""
oauth_server.py — TikTok OAuth 2.0 login flow.

How it works (in plain English):
  1. Opens your browser to TikTok's login page
  2. You log in and click "Authorize"
  3. TikTok redirects back to a tiny web server running on your computer
  4. That server catches the authorization code
  5. We exchange that code for an access token (the "temporary password")
  6. The token is saved to data/tokens/ so we don't have to log in every time

The access token expires after 24 hours, but the refresh token lasts 365 days.
We auto-refresh when needed so you rarely have to re-login.
"""

import json
import secrets
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from rich import print as rprint

from src.utils.config import (
    TIKTOK_CLIENT_KEY,
    TIKTOK_CLIENT_SECRET,
    DATA_TOKENS_DIR,
)

# ── Constants ──
TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
REDIRECT_PORT = 8585
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"

# We need these permissions to post videos and read creator info
# user.info.basic = read profile, video.upload = upload files, video.publish = post to feed
SCOPES = "user.info.basic,video.upload,video.publish"

# Where we store the token so you don't have to log in every time
TOKEN_DIR = DATA_TOKENS_DIR
TOKEN_FILE = TOKEN_DIR / "tiktok_token.json"


def _save_token(token_data: dict) -> None:
    """Save token to disk."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    token_data["saved_at"] = time.time()
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))


def load_token() -> dict | None:
    """Load saved token from disk. Returns None if no token exists."""
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def is_token_expired(token_data: dict) -> bool:
    """Check if the access token has expired (24h lifetime)."""
    saved_at = token_data.get("saved_at", 0)
    expires_in = token_data.get("expires_in", 86400)
    # Add 5-minute buffer so we refresh before it actually expires
    return time.time() > (saved_at + expires_in - 300)


def refresh_access_token(token_data: dict) -> dict | None:
    """
    Use the refresh token to get a new access token.
    This happens automatically when your token expires (every 24h).
    """
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return None

    rprint("[blue]Refreshing access token...[/blue]")

    resp = requests.post(TIKTOK_TOKEN_URL, data={
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    })

    if resp.status_code != 200:
        rprint(f"[red]Token refresh failed: {resp.status_code}[/red]")
        return None

    new_token = resp.json()
    if new_token.get("error", "") and new_token["error"] != "ok":
        rprint(f"[red]Token refresh error: {new_token.get('error_description', new_token)}[/red]")
        return None

    _save_token(new_token)
    rprint("[green]Token refreshed successfully[/green]")
    return new_token


def get_valid_token() -> dict | None:
    """
    Get a valid access token. Auto-refreshes if expired.
    Returns None if no token exists (need to run login flow).
    """
    token_data = load_token()
    if token_data is None:
        return None

    if is_token_expired(token_data):
        token_data = refresh_access_token(token_data)

    return token_data


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """
    Tiny web server that catches TikTok's redirect after you log in.
    When TikTok redirects to http://localhost:8585/callback?code=ABC123,
    this server grabs that code.
    """
    auth_code = None
    auth_state = None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)
            _OAuthCallbackHandler.auth_code = params.get("code", [None])[0]
            _OAuthCallbackHandler.auth_state = params.get("state", [None])[0]

            # Show a nice page in the browser
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
                b"<h1>&#10004; Logged in!</h1>"
                b"<p>You can close this tab and go back to the terminal.</p>"
                b"</body></html>"
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress noisy HTTP logs


def login() -> dict | None:
    """
    Run the full TikTok OAuth login flow.

    Opens your browser → you log in → we get a token.
    Returns the token data dict, or None if it fails.
    """
    if not TIKTOK_CLIENT_KEY or not TIKTOK_CLIENT_SECRET:
        rprint("[red]ERROR: TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET must be set in .env[/red]")
        return None

    # Generate a random state value to prevent CSRF attacks
    state = secrets.token_urlsafe(32)

    # Build the TikTok authorization URL
    auth_params = {
        "client_key": TIKTOK_CLIENT_KEY,
        "response_type": "code",
        "scope": SCOPES,
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }
    auth_url = f"{TIKTOK_AUTH_URL}?{urlencode(auth_params)}"

    # Reset the callback handler
    _OAuthCallbackHandler.auth_code = None
    _OAuthCallbackHandler.auth_state = None

    # Start a temporary web server to catch the callback.
    # We loop handle_request() up to 5 times because browsers often send
    # extra requests (like GET /favicon.ico) that would consume a single handler.
    server = HTTPServer(("localhost", REDIRECT_PORT), _OAuthCallbackHandler)
    server.timeout = 120  # 2-minute overall timeout

    def _serve_until_code():
        for _ in range(5):
            server.handle_request()
            if _OAuthCallbackHandler.auth_code:
                break

    server_thread = threading.Thread(target=_serve_until_code, daemon=True)
    server_thread.start()

    rprint("\n[bold blue]Opening TikTok login in your browser...[/bold blue]")
    rprint(f"[dim]If the browser doesn't open, go to:[/dim]")
    rprint(f"[dim]{auth_url}[/dim]\n")
    webbrowser.open(auth_url)

    # Wait for the callback (up to 2 minutes)
    rprint("[yellow]Waiting for you to log in... (2 minute timeout)[/yellow]")
    server_thread.join(timeout=120)
    server.server_close()

    code = _OAuthCallbackHandler.auth_code
    returned_state = _OAuthCallbackHandler.auth_state

    if not code:
        rprint("[red]Login timed out or was cancelled.[/red]")
        return None

    # Verify state to prevent CSRF
    if returned_state != state:
        rprint("[red]Security error: state mismatch. Try again.[/red]")
        return None

    # Exchange the authorization code for an access token
    rprint("[blue]Exchanging code for access token...[/blue]")
    resp = requests.post(TIKTOK_TOKEN_URL, data={
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    })

    if resp.status_code != 200:
        rprint(f"[red]Token exchange failed: {resp.status_code} {resp.text}[/red]")
        return None

    token_data = resp.json()
    if token_data.get("error", "") and token_data["error"] != "ok":
        rprint(f"[red]Token error: {token_data.get('error_description', token_data)}[/red]")
        return None

    _save_token(token_data)
    rprint("[green]Login successful! Token saved.[/green]")
    return token_data


# ── Run standalone for testing ──
if __name__ == "__main__":
    rprint("[bold blue]TikTok OAuth Login[/bold blue]")
    rprint("-" * 40)

    existing = get_valid_token()
    if existing:
        rprint("[green]Already logged in (valid token found)[/green]")
        rprint(f"  Open ID: {existing.get('open_id', 'N/A')}")
    else:
        rprint("No valid token found. Starting login flow...")
        login()
