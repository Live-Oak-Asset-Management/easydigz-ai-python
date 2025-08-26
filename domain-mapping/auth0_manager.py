#!/usr/bin/env python3
"""
Auth0 Client URL Manager

Manages callbacks, allowed_logout_urls, and web_origins for an Auth0 application.
- Adds and removes domain entries (with optional www/non-www variants)
- Lists current configuration
- Fetches and caches Auth0 Management API tokens automatically

Environment variables expected in a .env file colocated with this script:
  AUTH0_DOMAIN=your-tenant.auth0.com
  AUTH0_CLIENT_ID=machine-to-machine-app-client-id
  AUTH0_CLIENT_SECRET=machine-to-machine-app-client-secret
  AUTH0_APP_CLIENT_ID=application-client-id-to-update  # optional if you pass client_id via CLI

Required Auth0 Management API scopes for the M2M app:
  read:clients, update:clients

Usage (PowerShell examples):
  # Add domain (adds https://{domain}/callback, https://{domain}/, logout + web origins)
  python .\auth0_manager.py add portal.example.com [optional-client-id]

  # Remove domain
  python .\auth0_manager.py remove portal.example.com [optional-client-id]

  # List URLs
  python .\auth0_manager.py list [optional-client-id]
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

# --- Load environment variables from .env next to this file ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, ".env")
if not os.path.exists(ENV_PATH):
    print(f"Warning: env file not found at: {ENV_PATH}")
    print("Please make sure you have Auth0 credentials set.")
load_dotenv(dotenv_path=ENV_PATH)

# --- Auth0 configuration ---
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "").strip()
AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID", "").strip()
AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET", "").strip()
AUTH0_APP_CLIENT_ID = os.getenv("AUTH0_APP_CLIENT_ID", "").strip()

# --- Token cache ---
_token_cache: Dict[str, Optional[str]] = {
    "access_token": None,
    "expires_at": None,  # datetime
}


# --- Helpers (aligned with existing domain normalization style) ---
def normalize_domain(d: str) -> str:
    d = (d or "").strip().lower()
    if d.startswith("http://"):
        d = d[7:]
    elif d.startswith("https://"):
        d = d[8:]
    d = d.strip("/")
    if d.endswith("."):
        d = d[:-1]
    return d


def domain_variants(custom_domain: str) -> List[str]:
    base = normalize_domain(custom_domain)
    base_no_www = base[4:] if base.startswith("www.") else base
    variants: List[str] = []
    for v in [base_no_www, f"www.{base_no_www}"]:
        if v and v not in variants:
            variants.append(v)
    return variants


# --- Auth0 token management ---
def get_management_token() -> Optional[str]:
    """Get or refresh an Auth0 Management API token using client credentials."""
    access_token = _token_cache.get("access_token")
    expires_at = _token_cache.get("expires_at")
    if access_token and isinstance(expires_at, datetime) and datetime.now() < expires_at:
        return access_token

    if not (AUTH0_DOMAIN and AUTH0_CLIENT_ID and AUTH0_CLIENT_SECRET):
        print("Error: AUTH0_DOMAIN, AUTH0_CLIENT_ID, or AUTH0_CLIENT_SECRET not set in .env")
        return None

    try:
        url = f"https://{AUTH0_DOMAIN}/oauth/token"
        payload = {
            "client_id": AUTH0_CLIENT_ID,
            "client_secret": AUTH0_CLIENT_SECRET,
            "audience": f"https://{AUTH0_DOMAIN}/api/v2/",
            "grant_type": "client_credentials",
        }
        resp = requests.post(url, json=payload, timeout=25)
        resp.raise_for_status()
        data = resp.json() or {}
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 86400))
        if not token:
            print(f"Error: No access_token in response: {data}")
            return None
        # cache token (refresh 60s before expiry)
        _token_cache["access_token"] = token
        _token_cache["expires_at"] = datetime.now() + timedelta(seconds=max(0, expires_in - 60))
        return token
    except requests.RequestException as e:
        print(f"Error obtaining Auth0 management token: {e}")
        try:
            if e.response is not None:
                print(json.dumps(e.response.json(), indent=2))
        except Exception:
            try:
                print(e.response.text)  # type: ignore[attr-defined]
            except Exception:
                pass
        return None


# --- Auth0 client operations ---
def get_client_details(client_id: Optional[str] = None) -> Optional[Dict]:
    token = get_management_token()
    if not token:
        return None
    client_id = (client_id or AUTH0_APP_CLIENT_ID or "").strip()
    if not client_id:
        print("Error: No client_id provided and AUTH0_APP_CLIENT_ID not set")
        return None
    try:
        url = f"https://{AUTH0_DOMAIN}/api/v2/clients/{client_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = requests.get(url, headers=headers, timeout=25)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"Error getting client details: {e}")
        try:
            if e.response is not None:
                print(json.dumps(e.response.json(), indent=2))
        except Exception:
            try:
                print(e.response.text)  # type: ignore[attr-defined]
            except Exception:
                pass
        return None


def _ensure_list(v):
    return list(v or []) if isinstance(v, list) else ([] if v in (None, "") else [v])


def update_client_urls(
    custom_domain: str,
    client_id: Optional[str] = None,
    add_variants: bool = True,
    protocol: str = "https",
) -> Dict:
    """Add domain entries to callbacks, allowed_logout_urls, and web_origins."""
    client_id = (client_id or AUTH0_APP_CLIENT_ID or "").strip()
    if not client_id:
        msg = "Error: No client_id provided and AUTH0_APP_CLIENT_ID not set"
        print(msg)
        return {"success": False, "message": msg, "domain": custom_domain}

    current = get_client_details(client_id)
    if not current:
        msg = f"Failed to get current configuration for client {client_id}"
        print(msg)
        return {"success": False, "message": msg, "domain": custom_domain, "client_id": client_id}

    domains = domain_variants(custom_domain) if add_variants else [normalize_domain(custom_domain)]
    print(f"Processing domains: {domains}")

    callbacks = _ensure_list(current.get("callbacks"))
    logout_urls = _ensure_list(current.get("allowed_logout_urls"))
    web_origins = _ensure_list(current.get("web_origins"))

    added_callbacks: List[str] = []
    added_logout_urls: List[str] = []
    added_web_origins: List[str] = []

    for d in domains:
        callback_url = f"{protocol}://{d}/callback"
        if callback_url not in callbacks:
            callbacks.append(callback_url)
            added_callbacks.append(callback_url)
        root_callback = f"{protocol}://{d}/"
        if root_callback not in callbacks:
            callbacks.append(root_callback)
            added_callbacks.append(root_callback)

        base_url = f"{protocol}://{d}"
        if base_url not in logout_urls:
            logout_urls.append(base_url)
            added_logout_urls.append(base_url)
        if base_url not in web_origins:
            web_origins.append(base_url)
            added_web_origins.append(base_url)

    if not (added_callbacks or added_logout_urls or added_web_origins):
        msg = f"All URLs for '{custom_domain}' already exist in Auth0 configuration"
        print(msg)
        return {
            "success": True,
            "message": msg,
            "domain": custom_domain,
            "client_id": client_id,
            "status": "no_changes",
        }

    update_payload = {
        "callbacks": callbacks,
        "allowed_logout_urls": logout_urls,
        "web_origins": web_origins,
    }

    token = get_management_token()
    if not token:
        msg = "Failed to get management token for update"
        print(msg)
        return {"success": False, "message": msg, "domain": custom_domain, "client_id": client_id}

    try:
        url = f"https://{AUTH0_DOMAIN}/api/v2/clients/{client_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        print(f"Updating Auth0 client {client_id}...")
        resp = requests.patch(url, json=update_payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result = {
            "success": True,
            "message": f"Successfully added domain '{custom_domain}' to Auth0 configuration",
            "domain": custom_domain,
            "client_id": client_id,
            "added": {
                "callbacks": added_callbacks,
                "allowed_logout_urls": added_logout_urls,
                "web_origins": added_web_origins,
            },
            "total": {
                "callbacks": len(callbacks),
                "allowed_logout_urls": len(logout_urls),
                "web_origins": len(web_origins),
            },
        }
        print(json.dumps(result))
        return result
    except requests.RequestException as e:
        msg = f"Error updating Auth0 client: {e}"
        print(msg)
        try:
            if e.response is not None:
                print(json.dumps(e.response.json(), indent=2))
        except Exception:
            try:
                print(e.response.text)  # type: ignore[attr-defined]
            except Exception:
                pass
        return {"success": False, "message": msg, "domain": custom_domain, "client_id": client_id}


def remove_client_urls(
    custom_domain: str,
    client_id: Optional[str] = None,
    remove_variants: bool = True,
) -> Dict:
    """Remove domain entries from callbacks, allowed_logout_urls, and web_origins."""
    client_id = (client_id or AUTH0_APP_CLIENT_ID or "").strip()
    if not client_id:
        msg = "Error: No client_id provided and AUTH0_APP_CLIENT_ID not set"
        print(msg)
        return {"success": False, "message": msg, "domain": custom_domain}

    current = get_client_details(client_id)
    if not current:
        msg = f"Failed to get current configuration for client {client_id}"
        print(msg)
        return {"success": False, "message": msg, "domain": custom_domain, "client_id": client_id}

    domains = domain_variants(custom_domain) if remove_variants else [normalize_domain(custom_domain)]
    print(f"Removing domains: {domains}")

    callbacks = _ensure_list(current.get("callbacks"))
    logout_urls = _ensure_list(current.get("allowed_logout_urls"))
    web_origins = _ensure_list(current.get("web_origins"))

    removed_callbacks: List[str] = []
    removed_logout_urls: List[str] = []
    removed_web_origins: List[str] = []

    for d in domains:
        patterns = [
            f"https://{d}/callback",
            f"https://{d}/",
            f"https://{d}",
            f"http://{d}/callback",
            f"http://{d}/",
            f"http://{d}",
        ]
        for p in list(patterns):
            if p in callbacks:
                callbacks.remove(p)
                removed_callbacks.append(p)
        for proto in ["https", "http"]:
            base = f"{proto}://{d}"
            if base in logout_urls:
                logout_urls.remove(base)
                removed_logout_urls.append(base)
            if base in web_origins:
                web_origins.remove(base)
                removed_web_origins.append(base)

    if not (removed_callbacks or removed_logout_urls or removed_web_origins):
        msg = f"No URLs for '{custom_domain}' found in Auth0 configuration"
        print(msg)
        return {
            "success": True,
            "message": msg,
            "domain": custom_domain,
            "client_id": client_id,
            "status": "not_found",
        }

    update_payload = {
        "callbacks": callbacks,
        "allowed_logout_urls": logout_urls,
        "web_origins": web_origins,
    }

    token = get_management_token()
    if not token:
        msg = "Failed to get management token for update"
        print(msg)
        return {"success": False, "message": msg, "domain": custom_domain, "client_id": client_id}

    try:
        url = f"https://{AUTH0_DOMAIN}/api/v2/clients/{client_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        print(f"Updating Auth0 client {client_id}...")
        resp = requests.patch(url, json=update_payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result = {
            "success": True,
            "message": f"Successfully removed domain '{custom_domain}' from Auth0 configuration",
            "domain": custom_domain,
            "client_id": client_id,
            "removed": {
                "callbacks": removed_callbacks,
                "allowed_logout_urls": removed_logout_urls,
                "web_origins": removed_web_origins,
            },
            "remaining": {
                "callbacks": len(callbacks),
                "allowed_logout_urls": len(logout_urls),
                "web_origins": len(web_origins),
            },
        }
        print(json.dumps(result))
        return result
    except requests.RequestException as e:
        msg = f"Error updating Auth0 client: {e}"
        print(msg)
        try:
            if e.response is not None:
                print(json.dumps(e.response.json(), indent=2))
        except Exception:
            try:
                print(e.response.text)  # type: ignore[attr-defined]
            except Exception:
                pass
        return {"success": False, "message": msg, "domain": custom_domain, "client_id": client_id}


def list_client_urls(client_id: Optional[str] = None) -> Dict:
    client_id = (client_id or AUTH0_APP_CLIENT_ID or "").strip()
    if not client_id:
        msg = "Error: No client_id provided and AUTH0_APP_CLIENT_ID not set"
        print(msg)
        return {"success": False, "message": msg}

    current = get_client_details(client_id)
    if not current:
        msg = f"Failed to get configuration for client {client_id}"
        print(msg)
        return {"success": False, "message": msg, "client_id": client_id}

    result = {
        "success": True,
        "client_id": client_id,
        "client_name": current.get("name", "Unknown"),
        "callbacks": _ensure_list(current.get("callbacks")),
        "allowed_logout_urls": _ensure_list(current.get("allowed_logout_urls")),
        "web_origins": _ensure_list(current.get("web_origins")),
    }
    print(json.dumps(result))
    return result


def derive_logout_and_origins_from_callbacks(callbacks: List[str]) -> tuple[List[str], List[str]]:
    """Extract base URLs from callbacks to populate allowed_logout_urls and web_origins."""
    from urllib.parse import urlparse
    logout_urls = set()
    web_origins = set()
    
    for url in callbacks or []:
        try:
            u = urlparse(url)
            if not u.scheme or not u.netloc:
                continue
            base_url = f"{u.scheme}://{u.netloc}"
            logout_url = f"{u.scheme}://{u.netloc}/login"
            logout_urls.add(logout_url)
            web_origins.add(base_url)
        except Exception:
            continue
    
    return sorted(logout_urls), sorted(web_origins)


def add_domain_to_all_sections(
    domain_url: str,
    client_id: Optional[str] = None
) -> Dict:
    """Add exact domain URL to all three sections: callbacks, allowed_logout_urls, and web_origins.
    No domain manipulation - uses exactly what the user provides."""
    client_id = (client_id or AUTH0_APP_CLIENT_ID or "").strip()
    if not client_id:
        msg = "Error: No client_id provided and AUTH0_APP_CLIENT_ID not set"
        print(msg)
        return {"success": False, "message": msg, "domain": domain_url}

    current = get_client_details(client_id)
    if not current:
        msg = f"Failed to get current configuration for client {client_id}"
        print(msg)
        return {"success": False, "message": msg, "domain": domain_url, "client_id": client_id}

    # Use exactly what user provided - no variants, no manipulation
    # Debug info goes to stderr so it doesn't interfere with JSON parsing
    import sys
    print(f"Adding to all sections for exact URL: {domain_url}", file=sys.stderr)

    callbacks = _ensure_list(current.get("callbacks"))
    logout_urls = _ensure_list(current.get("allowed_logout_urls"))
    web_origins = _ensure_list(current.get("web_origins"))

    added_callbacks: List[str] = []
    added_logout_urls: List[str] = []
    added_web_origins: List[str] = []

    # Parse the provided URL to extract components
    from urllib.parse import urlparse
    try:
        parsed = urlparse(domain_url)
        if not parsed.scheme or not parsed.netloc:
            msg = f"Invalid URL format: {domain_url}. Please provide full URL like https://example.com"
            print(msg)
            return {"success": False, "message": msg, "domain": domain_url, "client_id": client_id}
        
        base_url = f"{parsed.scheme}://{parsed.netloc}"
    except Exception as e:
        msg = f"Error parsing URL {domain_url}: {e}"
        print(msg)
        return {"success": False, "message": msg, "domain": domain_url, "client_id": client_id}

    # Callbacks: exact base URL + callback endpoint
    callback_url = f"{base_url}/api/auth/callback"
    
    if base_url not in callbacks:
        callbacks.append(base_url)
        added_callbacks.append(base_url)
    if callback_url not in callbacks:
        callbacks.append(callback_url)
        added_callbacks.append(callback_url)

    # Logout URLs: exact base URL + /login
    logout_url = f"{base_url}/login"
    if logout_url not in logout_urls:
        logout_urls.append(logout_url)
        added_logout_urls.append(logout_url)
    
    # Web Origins: exact base URL
    if base_url not in web_origins:
        web_origins.append(base_url)
        added_web_origins.append(base_url)

    if not (added_callbacks or added_logout_urls or added_web_origins):
        msg = f"All URLs for '{domain_url}' already exist in Auth0 configuration"
        print(msg)
        return {
            "success": True,
            "message": msg,
            "domain": domain_url,
            "client_id": client_id,
            "status": "no_changes",
        }

    update_payload = {
        "callbacks": callbacks,
        "allowed_logout_urls": logout_urls,
        "web_origins": web_origins,
    }

    token = get_management_token()
    if not token:
        msg = "Failed to get management token for add-domain update"
        print(msg)
        return {"success": False, "message": msg, "domain": domain_url, "client_id": client_id}

    try:
        url = f"https://{AUTH0_DOMAIN}/api/v2/clients/{client_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        print(f"Adding exact domain '{domain_url}' to all Auth0 sections...", file=sys.stderr)
        resp = requests.patch(url, json=update_payload, headers=headers, timeout=30)
        resp.raise_for_status()
        
        result = {
            "success": True,
            "message": f"Successfully added domain '{domain_url}' to all Auth0 sections",
            "domain": domain_url,
            "client_id": client_id,
            "added": {
                "callbacks": added_callbacks,
                "allowed_logout_urls": added_logout_urls,
                "web_origins": added_web_origins,
            },
            "total": {
                "callbacks": len(callbacks),
                "allowed_logout_urls": len(logout_urls),
                "web_origins": len(web_origins),
            },
        }
        print(json.dumps(result))
        return result
        
    except requests.RequestException as e:
        msg = f"Error updating Auth0 client (add-domain): {e}"
        print(msg)
        try:
            if e.response is not None:
                print(json.dumps(e.response.json(), indent=2))
        except Exception:
            try:
                print(e.response.text)  # type: ignore[attr-defined]
            except Exception:
                pass
        return {"success": False, "message": msg, "domain": domain_url, "client_id": client_id}


def remove_domain_from_all_sections(
    domain_url: str,
    client_id: Optional[str] = None
) -> Dict:
    """Remove exact domain URL from all three sections: callbacks, allowed_logout_urls, and web_origins.
    No domain manipulation - removes exactly what the user provides."""
    client_id = (client_id or AUTH0_APP_CLIENT_ID or "").strip()
    if not client_id:
        msg = "Error: No client_id provided and AUTH0_APP_CLIENT_ID not set"
        print(msg)
        return {"success": False, "message": msg, "domain": domain_url}

    current = get_client_details(client_id)
    if not current:
        msg = f"Failed to get current configuration for client {client_id}"
        print(msg)
        return {"success": False, "message": msg, "domain": domain_url, "client_id": client_id}

    # Use exactly what user provided - no variants, no manipulation
    import sys
    print(f"Removing from all sections for exact URL: {domain_url}", file=sys.stderr)

    callbacks = _ensure_list(current.get("callbacks"))
    logout_urls = _ensure_list(current.get("allowed_logout_urls"))
    web_origins = _ensure_list(current.get("web_origins"))

    removed_callbacks: List[str] = []
    removed_logout_urls: List[str] = []
    removed_web_origins: List[str] = []

    # Parse the provided URL to extract components
    from urllib.parse import urlparse
    try:
        parsed = urlparse(domain_url)
        if not parsed.scheme or not parsed.netloc:
            msg = f"Invalid URL format: {domain_url}. Please provide full URL like https://example.com"
            print(msg)
            return {"success": False, "message": msg, "domain": domain_url, "client_id": client_id}
        
        base_url = f"{parsed.scheme}://{parsed.netloc}"
    except Exception as e:
        msg = f"Error parsing URL {domain_url}: {e}"
        print(msg)
        return {"success": False, "message": msg, "domain": domain_url, "client_id": client_id}

    # Remove callbacks: exact base URL + callback endpoint
    callback_url = f"{base_url}/api/auth/callback"
    
    if base_url in callbacks:
        callbacks.remove(base_url)
        removed_callbacks.append(base_url)
    if callback_url in callbacks:
        callbacks.remove(callback_url)
        removed_callbacks.append(callback_url)

    # Remove logout URLs: exact base URL + /login
    logout_url = f"{base_url}/login"
    if logout_url in logout_urls:
        logout_urls.remove(logout_url)
        removed_logout_urls.append(logout_url)
    
    # Remove web origins: exact base URL
    if base_url in web_origins:
        web_origins.remove(base_url)
        removed_web_origins.append(base_url)

    if not (removed_callbacks or removed_logout_urls or removed_web_origins):
        msg = f"No URLs for '{domain_url}' found in Auth0 configuration"
        print(msg)
        return {
            "success": True,
            "message": msg,
            "domain": domain_url,
            "client_id": client_id,
            "status": "not_found",
        }

    update_payload = {
        "callbacks": callbacks,
        "allowed_logout_urls": logout_urls,
        "web_origins": web_origins,
    }

    token = get_management_token()
    if not token:
        msg = "Failed to get management token for remove-domain update"
        print(msg)
        return {"success": False, "message": msg, "domain": domain_url, "client_id": client_id}

    try:
        url = f"https://{AUTH0_DOMAIN}/api/v2/clients/{client_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        print(f"Removing exact domain '{domain_url}' from all Auth0 sections...", file=sys.stderr)
        resp = requests.patch(url, json=update_payload, headers=headers, timeout=30)
        resp.raise_for_status()
        
        result = {
            "success": True,
            "message": f"Successfully removed domain '{domain_url}' from all Auth0 sections",
            "domain": domain_url,
            "client_id": client_id,
            "removed": {
                "callbacks": removed_callbacks,
                "allowed_logout_urls": removed_logout_urls,
                "web_origins": removed_web_origins,
            },
            "remaining": {
                "callbacks": len(callbacks),
                "allowed_logout_urls": len(logout_urls),
                "web_origins": len(web_origins),
            },
        }
        print(json.dumps(result))
        return result
        
    except requests.RequestException as e:
        msg = f"Error updating Auth0 client (remove-domain): {e}"
        print(msg)
        try:
            if e.response is not None:
                print(json.dumps(e.response.json(), indent=2))
        except Exception:
            try:
                print(e.response.text)  # type: ignore[attr-defined]
            except Exception:
                pass
        return {"success": False, "message": msg, "domain": domain_url, "client_id": client_id}


def set_web_origins(web_origins_list: List[str], client_id: Optional[str] = None, apply: bool = True) -> Dict:
    """Set specific web origins for the Auth0 client."""
    client_id = (client_id or AUTH0_APP_CLIENT_ID or "").strip()
    if not client_id:
        msg = "Error: No client_id provided and AUTH0_APP_CLIENT_ID not set"
        print(msg)
        return {"success": False, "message": msg}

    current = get_client_details(client_id)
    if not current:
        msg = f"Failed to get configuration for client {client_id}"
        print(msg)
        return {"success": False, "message": msg, "client_id": client_id}

    old_origins = _ensure_list(current.get("web_origins"))
    new_origins = _uniq(web_origins_list)  # Remove duplicates while preserving order

    changed = new_origins != old_origins

    result = {
        "success": True,
        "client_id": client_id,
        "changed": changed,
        "before": {
            "web_origins": old_origins,
        },
        "after": {
            "web_origins": new_origins,
        },
    }

    if not changed or not apply:
        print(json.dumps(result))
        return result

    token = get_management_token()
    if not token:
        msg = "Failed to get management token for web origins update"
        print(msg)
        return {"success": False, "message": msg, "client_id": client_id}

    try:
        url = f"https://{AUTH0_DOMAIN}/api/v2/clients/{client_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        update_payload = {
            "web_origins": new_origins,
        }
        resp = requests.patch(url, json=update_payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result["message"] = f"Web origins updated with {len(new_origins)} entries"
        print(json.dumps(result))
        return result
    except requests.RequestException as e:
        msg = f"Error updating Auth0 client web origins: {e}"
        print(msg)
        try:
            if e.response is not None:
                print(json.dumps(e.response.json(), indent=2))
        except Exception:
            try:
                print(e.response.text)  # type: ignore[attr-defined]
            except Exception:
                pass
        return {"success": False, "message": msg, "client_id": client_id}


def populate_logout_and_origins(client_id: Optional[str] = None, apply: bool = True) -> Dict:
    """Populate allowed_logout_urls and web_origins from existing callbacks."""
    client_id = (client_id or AUTH0_APP_CLIENT_ID or "").strip()
    if not client_id:
        msg = "Error: No client_id provided and AUTH0_APP_CLIENT_ID not set"
        print(msg)
        return {"success": False, "message": msg}

    current = get_client_details(client_id)
    if not current:
        msg = f"Failed to get configuration for client {client_id}"
        print(msg)
        return {"success": False, "message": msg, "client_id": client_id}

    callbacks = _ensure_list(current.get("callbacks"))
    old_logout = _ensure_list(current.get("allowed_logout_urls"))
    old_origins = _ensure_list(current.get("web_origins"))

    # Derive new logout URLs and web origins from callbacks
    new_logout, new_origins = derive_logout_and_origins_from_callbacks(callbacks)

    changed = (new_logout != old_logout) or (new_origins != old_origins)

    result = {
        "success": True,
        "client_id": client_id,
        "changed": changed,
        "before": {
            "allowed_logout_urls": old_logout,
            "web_origins": old_origins,
        },
        "after": {
            "allowed_logout_urls": new_logout,
            "web_origins": new_origins,
        },
    }

    if not changed or not apply:
        print(json.dumps(result))
        return result

    token = get_management_token()
    if not token:
        msg = "Failed to get management token for populate update"
        print(msg)
        return {"success": False, "message": msg, "client_id": client_id}

    try:
        url = f"https://{AUTH0_DOMAIN}/api/v2/clients/{client_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        update_payload = {
            "allowed_logout_urls": new_logout,
            "web_origins": new_origins,
        }
        resp = requests.patch(url, json=update_payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result["message"] = "Logout URLs and web origins populated from callbacks"
        print(json.dumps(result))
        return result
    except requests.RequestException as e:
        msg = f"Error updating Auth0 client (populate): {e}"
        print(msg)
        try:
            if e.response is not None:
                print(json.dumps(e.response.json(), indent=2))
        except Exception:
            try:
                print(e.response.text)  # type: ignore[attr-defined]
            except Exception:
                pass
        return {"success": False, "message": msg, "client_id": client_id}


def _print_usage() -> None:
    print("Usage:")
    print("  Add domain:     python auth0_manager.py add <domain> [client_id]")
    print("  Remove domain:  python auth0_manager.py remove <domain> [client_id]")
    print("  List URLs:      python auth0_manager.py list [client_id]")
    print("  Canonicalize:   python auth0_manager.py canonicalize [client_id]")
    print("  Populate:       python auth0_manager.py populate [client_id]")
    print("  Set origins:    python auth0_manager.py set-origins <comma-separated-urls> [client_id]")
    print("  Add to all:     python auth0_manager.py add-all <domain> [client_id]")
    print("  Remove from all: python auth0_manager.py remove-all <domain> [client_id]")
    print("")
    print("Examples:")
    print("  python auth0_manager.py add portal.example.com")
    print("  python auth0_manager.py remove portal.example.com")
    print("  python auth0_manager.py list")
    print("  python auth0_manager.py canonicalize")
    print("  python auth0_manager.py populate")
    print("  python auth0_manager.py set-origins 'https://example.com,http://localhost:3000'")
    print("  python auth0_manager.py add-all https://portal.example.com")
    print("  python auth0_manager.py remove-all https://portal.example.com")


# === Canonicalization helpers ===
def _split_host_port(netloc: str):
    if not netloc:
        return "", None
    if netloc.count(":") == 1 and netloc.rsplit(":", 1)[1].isdigit():
        h, p = netloc.rsplit(":", 1)
        try:
            return h.lower(), int(p)
        except Exception:
            return netloc.lower(), None
    return netloc.lower(), None


_MULTI_TLDS = {
    "co.uk", "org.uk", "ac.uk", "gov.uk",
    "co.in", "net.in", "org.in", "firm.in", "gen.in", "ind.in",
    "com.au", "net.au", "org.au",
}


def _is_localhost(host: str) -> bool:
    h = (host or "").lower()
    # Treat only exact 'localhost' as non-wildcardable; subdomain.localhost can be folded
    return h == "localhost"


def _base_domain(host: str) -> str:
    """Approximate registrable base domain without external deps.
    Handles common multi-label TLDs used in this project (co.in, com.au, co.uk ...).
    Special case: .localhost domains always return 'localhost' as base.
    """
    host = (host or "").strip(".").lower()
    if not host:
        return host
    if _is_localhost(host):
        return host
    # Special handling for .localhost domains
    if host.endswith(".localhost"):
        return "localhost"
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    last2 = ".".join(labels[-2:])
    if last2 in _MULTI_TLDS and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last2


def _path_category(path: str) -> str:
    p = (path or "").strip()
    if p == "" or p == "/":
        return "root"
    # common callback paths
    if p.rstrip("/") in ("/api/auth/callback", "/callback"):
        return "callback"
    return "other"


def _uniq(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for s in seq:
        if s not in seen:
            out.append(s)
            seen.add(s)
    return out


def canonicalize_callbacks(callbacks: List[str]) -> List[str]:
    from urllib.parse import urlparse
    keep_exact: List[str] = []   # localhost and other-paths
    add_apex: List[str] = []
    want_wildcard = set()  # tuples: (scheme, base, category)

    for url in callbacks or []:
        try:
            u = urlparse(url)
        except Exception:
            keep_exact.append(url)
            continue
        scheme = (u.scheme or "").lower()
        host, port = _split_host_port(u.netloc)
        if not scheme or not host:
            keep_exact.append(url)
            continue
        if _is_localhost(host):
            # Keep exact for plain localhost (with or without port)
            keep_exact.append(url)
            continue
        base = _base_domain(host)
        category = _path_category(u.path)

        if host == base:
            # apex — keep exact (normalized)
            port_s = f":{port}" if port else ""
            norm = f"{scheme}://{base}{port_s}{'' if category == 'other' else ('/api/auth/callback' if category == 'callback' else '/') }"
            # Try to preserve exact input path if 'other'
            if category == "other":
                norm = f"{scheme}://{host}{f':{port}' if port else ''}{u.path}"
            if norm not in add_apex and norm not in keep_exact:
                add_apex.append(norm)
        else:
            # subdomain — prefer wildcard by category
            if category in ("root", "callback"):
                want_wildcard.add((scheme, base, category, port))
            else:
                # unknown paths: keep exact
                keep_exact.append(url)

    # materialize wildcards - prefer https over http for same domain/category/port
    wildcard_by_key = {}  # (base, category, port) -> preferred scheme
    for scheme, base, category, port in want_wildcard:
        key = (base, category, port)
        if key not in wildcard_by_key or scheme == "https":
            wildcard_by_key[key] = scheme

    wildcard_urls: List[str] = []
    for (base, category, port), scheme in sorted(wildcard_by_key.items()):
        port_s = f":{port}" if port else ""
        if category == "root":
            wildcard_urls.append(f"{scheme}://*.{base}{port_s}")
        elif category == "callback":
            wildcard_urls.append(f"{scheme}://*.{base}{port_s}/api/auth/callback")

    # Compose final unique list, keep stable-ish ordering
    return _uniq(add_apex + wildcard_urls + keep_exact)


def canonicalize_simple_urls(urls: List[str]) -> List[str]:
    """Canonicalize logout urls or web origins: wildcard subdomains, keep apex and localhost exact.
    Any entries that include a path are kept exact (no folding).
    """
    from urllib.parse import urlparse
    keep_exact: List[str] = []
    add_apex: List[str] = []
    want_wildcard = set()  # (scheme, base, port)

    for url in urls or []:
        try:
            u = urlparse(url)
        except Exception:
            keep_exact.append(url)
            continue
        scheme = (u.scheme or "").lower()
        host, port = _split_host_port(u.netloc)
        path = (u.path or "")
        if not scheme or not host:
            keep_exact.append(url)
            continue
        # keep exact for plain localhost or when path present
        if _is_localhost(host) or path not in ("", "/"):
            keep_exact.append(url)
            continue
        base = _base_domain(host)
        if host == base:
            apex = f"{scheme}://{base}{f':{port}' if port else ''}"
            if apex not in add_apex and apex not in keep_exact:
                add_apex.append(apex)
        else:
            want_wildcard.add((scheme, base, port))

    wildcard_by_key = {}  # (base, port) -> preferred scheme
    for scheme, base, port in want_wildcard:
        key = (base, port)
        if key not in wildcard_by_key or scheme == "https":
            wildcard_by_key[key] = scheme

    wildcard_urls: List[str] = [
        f"{scheme}://*.{base}{f':{port}' if port else ''}" 
        for (base, port), scheme in sorted(wildcard_by_key.items())
    ]
    return _uniq(add_apex + wildcard_urls + keep_exact)


def canonicalize_client_urls(client_id: Optional[str] = None, apply: bool = True) -> Dict:
    client_id = (client_id or AUTH0_APP_CLIENT_ID or "").strip()
    if not client_id:
        msg = "Error: No client_id provided and AUTH0_APP_CLIENT_ID not set"
        print(msg)
        return {"success": False, "message": msg}

    current = get_client_details(client_id)
    if not current:
        msg = f"Failed to get configuration for client {client_id}"
        print(msg)
        return {"success": False, "message": msg, "client_id": client_id}

    old_callbacks = _ensure_list(current.get("callbacks"))
    old_logout = _ensure_list(current.get("allowed_logout_urls"))
    old_origins = _ensure_list(current.get("web_origins"))

    new_callbacks = canonicalize_callbacks(old_callbacks)
    new_logout = canonicalize_simple_urls(old_logout)
    new_origins = canonicalize_simple_urls(old_origins)

    changed = (new_callbacks != old_callbacks) or (new_logout != old_logout) or (new_origins != old_origins)

    result = {
        "success": True,
        "client_id": client_id,
        "changed": changed,
        "before": {
            "callbacks": old_callbacks,
            "allowed_logout_urls": old_logout,
            "web_origins": old_origins,
        },
        "after": {
            "callbacks": new_callbacks,
            "allowed_logout_urls": new_logout,
            "web_origins": new_origins,
        },
    }

    if not changed or not apply:
        print(json.dumps(result))
        return result

    token = get_management_token()
    if not token:
        msg = "Failed to get management token for canonicalize update"
        print(msg)
        return {"success": False, "message": msg, "client_id": client_id}

    try:
        url = f"https://{AUTH0_DOMAIN}/api/v2/clients/{client_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        update_payload = {
            "callbacks": new_callbacks,
            "allowed_logout_urls": new_logout,
            "web_origins": new_origins,
        }
        resp = requests.patch(url, json=update_payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result["message"] = "Client URLs canonicalized and updated"
        print(json.dumps(result))
        return result
    except requests.RequestException as e:
        msg = f"Error updating Auth0 client (canonicalize): {e}"
        print(msg)
        try:
            if e.response is not None:
                print(json.dumps(e.response.json(), indent=2))
        except Exception:
            try:
                print(e.response.text)  # type: ignore[attr-defined]
            except Exception:
                pass
        return {"success": False, "message": msg, "client_id": client_id}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        _print_usage()
        sys.exit(1)

    action = (sys.argv[1] or "").strip().lower()

    if action == "add":
        if len(sys.argv) < 3:
            custom_domain = input("Enter the custom domain to add (e.g., portal.example.com): ").strip()
        else:
            custom_domain = sys.argv[2].strip()
        cid = sys.argv[3].strip() if len(sys.argv) > 3 else None
        res = update_client_urls(custom_domain, cid)
        sys.exit(0 if res.get("success") else 1)

    elif action == "remove":
        if len(sys.argv) < 3:
            custom_domain = input("Enter the custom domain to remove (e.g., portal.example.com): ").strip()
        else:
            custom_domain = sys.argv[2].strip()
        cid = sys.argv[3].strip() if len(sys.argv) > 3 else None
        res = remove_client_urls(custom_domain, cid)
        sys.exit(0 if res.get("success") else 1)

    elif action == "list":
        cid = sys.argv[2].strip() if len(sys.argv) > 2 else None
        res = list_client_urls(cid)
        sys.exit(0 if res.get("success") else 1)

    else:
        if action == "canonicalize":
            cid = sys.argv[2].strip() if len(sys.argv) > 2 else None
            res = canonicalize_client_urls(cid, apply=True)
            sys.exit(0 if res.get("success") else 1)
        elif action == "populate":
            cid = sys.argv[2].strip() if len(sys.argv) > 2 else None
            res = populate_logout_and_origins(cid, apply=True)
            sys.exit(0 if res.get("success") else 1)
        elif action == "set-origins":
            if len(sys.argv) < 3:
                origins_str = input("Enter comma-separated web origins: ").strip()
            else:
                origins_str = sys.argv[2].strip()
            cid = sys.argv[3].strip() if len(sys.argv) > 3 else None
            origins_list = [url.strip() for url in origins_str.split(",") if url.strip()]
            if not origins_list:
                print("Error: No web origins provided")
                sys.exit(1)
            res = set_web_origins(origins_list, cid, apply=True)
            sys.exit(0 if res.get("success") else 1)
        elif action == "add-all":
            if len(sys.argv) < 3:
                domain_url = input("Enter the full domain URL to add to all sections (e.g., https://portal.example.com): ").strip()
            else:
                domain_url = sys.argv[2].strip()
            cid = sys.argv[3].strip() if len(sys.argv) > 3 else None
            res = add_domain_to_all_sections(domain_url, cid)
            sys.exit(0 if res.get("success") else 1)
        elif action == "remove-all":
            if len(sys.argv) < 3:
                domain_url = input("Enter the full domain URL to remove from all sections (e.g., https://portal.example.com): ").strip()
            else:
                domain_url = sys.argv[2].strip()
            cid = sys.argv[3].strip() if len(sys.argv) > 3 else None
            res = remove_domain_from_all_sections(domain_url, cid)
            sys.exit(0 if res.get("success") else 1)
        else:
            print(f"Unknown action: {action}")
            _print_usage()
            sys.exit(1)
