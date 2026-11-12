#!/usr/bin/env python3
"""Sign-in for the OvO merchant site.

Three sign-ins exist, and they stay separate. A merchant signs
in to the OvO site. A merchant signs in to WordPress before
Install OvO Plugins. A merchant signs in a card as the go-live
gate for billing. Card sign-in is not the same as WordPress
sign-in. Both are needed, at different steps.

Passwords are hashed with scrypt. Session tokens are random
and stored as a hash only. WordPress passwords and app
passwords are never stored: they are used once, for one call,
then dropped. Card authorizations store a reference only:
brand and last four digits, never the card number. Nothing
here writes a secret to a log.
"""
import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

SESSION_HOURS = 24


def now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def hash_password(password, salt=None):
    """scrypt hash. Returns (hash_hex, salt_hex)."""
    if salt is None:
        salt = secrets.token_bytes(16)
    else:
        salt = bytes.fromhex(salt)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=16384, r=8, p=1, dklen=32)
    return digest.hex(), salt.hex()


def check_password(password, password_hash, password_salt):
    digest, _ = hash_password(password, password_salt)
    return secrets.compare_digest(digest, password_hash)


def create_merchant(store, merchant_id, name, email, password):
    """Create a merchant. The customer index sets the launch
    edition: the first 100 customers bill at the launch rate."""
    if store.get_merchant(merchant_id):
        raise ValueError(f"merchant already exists: {merchant_id}")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    password_hash, salt = hash_password(password)
    index = store.merchant_count() + 1
    store.create_merchant(merchant_id, name, email, password_hash, salt,
                          index, now_utc())
    return {"merchant_id": merchant_id, "name": name, "email": email,
            "customer_index": index}


def sign_in_ovo(store, merchant_id, password, store_id):
    """OvO site sign-in. Returns a session token and the session
    record. The token is shown once, to the merchant. Only its
    hash is stored."""
    merchant = store.get_merchant(merchant_id)
    if not merchant:
        return None, "unknown merchant"
    if not check_password(password, merchant["password_hash"],
                          merchant["password_salt"]):
        return None, "wrong password"
    if not store_id:
        return None, "store address is required"
    session_id = "sess-" + secrets.token_hex(12)
    token = secrets.token_urlsafe(32)
    issued = datetime.now(timezone.utc)
    expires = issued + timedelta(hours=SESSION_HOURS)
    store.create_session(session_id, merchant_id, store_id, "ovo", token,
                         issued.isoformat().replace("+00:00", "Z"),
                         expires.isoformat().replace("+00:00", "Z"))
    session = {"session_id": session_id, "merchant_id": merchant_id,
               "store_id": store_id, "submitted_by": "merchant",
               "expires_at_utc": expires.isoformat().replace("+00:00", "Z"),
               "revoked": False}
    return {"token": token, "session": session}, None


def verify_session(store, token, store_id):
    """Check a session token. Returns the session record, or
    (None, reason). An expired, revoked, or wrong-store session
    is refused."""
    row = store.get_session_by_token(token)
    if not row:
        return None, "unknown session"
    if row["revoked"]:
        return None, "session is revoked"
    expires = parse_iso(row["expires_at_utc"])
    if expires is None or expires <= datetime.now(timezone.utc):
        return None, "session is expired"
    if store_id and row["store_id"] != store_id:
        return None, "session is for a different store"
    return {"session_id": row["session_id"],
            "merchant_id": row["merchant_id"],
            "store_id": row["store_id"], "submitted_by": "merchant",
            "expires_at_utc": row["expires_at_utc"],
            "revoked": False}, None


def revoke_session(store, session_id):
    store.revoke_session(session_id)


def _default_http_get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode()


def verify_wordpress_signin(store_url, wp_username, app_password,
                            http_get=None):
    """WordPress sign-in, verified against the live store. Calls
    the store's own users endpoint with the app password and
    checks the user can manage the store. The app password is
    used for this one call only and is never stored or logged.
    Returns (verification, None) or (None, reason)."""
    http_get = http_get or _default_http_get
    if not store_url:
        return None, "store address is required"
    if not wp_username or not app_password:
        return None, "WordPress username and app password are required"
    url = store_url.rstrip("/") + "/wp-json/wp/v2/users/me"
    credentials = base64.b64encode(
        f"{wp_username}:{app_password}".encode()).decode()
    try:
        status, body = http_get(
            url, {"Authorization": f"Basic {credentials}"})
    except urllib.error.HTTPError as exc:
        return None, f"WordPress sign-in refused: HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"WordPress sign-in failed: store not reached ({exc})"
    if status != 200:
        return None, f"WordPress sign-in refused: HTTP {status}"
    try:
        user = json.loads(body)
    except ValueError:
        return None, "WordPress sign-in failed: bad response from store"
    capabilities = user.get("capabilities") or {}
    if capabilities and not capabilities.get("install_plugins"):
        return None, "WordPress user cannot install plugins"
    return {"store_url": store_url.rstrip("/"),
            "wp_username": wp_username,
            "wp_user_id": user.get("id"),
            "verified_at_utc": now_utc(),
            "method": "wordpress_app_password"}, None


def record_wordpress_signin(store, merchant_id, verification):
    """Record that a WordPress sign-in was verified. Only the
    username and the time are kept. No password is stored."""
    return store.record_wp_signin(
        merchant_id, verification["store_url"],
        verification["wp_username"], verification["verified_at_utc"],
        verification["method"])


def record_card_authorization(store, merchant_id, auth_ref, brand, last4):
    """Record a card authorization as the go-live gate. The
    authorization reference comes from the payment front end
    (a Stripe payment method id). Only the reference, the brand,
    and the last four digits are stored. A card number never
    reaches this code."""
    if not auth_ref or not isinstance(auth_ref, str):
        return None, "card authorization reference is missing"
    if not brand or not isinstance(brand, str):
        return None, "card brand is missing"
    if not (isinstance(last4, str) and len(last4) == 4 and last4.isdigit()):
        return None, "last four digits must be four digits"
    auth_id = store.record_card_auth(merchant_id, auth_ref, brand, last4,
                                     now_utc())
    return {"auth_id": auth_id, "merchant_id": merchant_id,
            "auth_ref": auth_ref, "brand": brand, "last4": last4,
            "authorized_at_utc": now_utc()}, None
