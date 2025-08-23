# helpers_cf.py
"""
Helpers for Cloudflare Custom Hostnames:
- get_custom_hostname_obj(domain)  -> pydantic model for the custom hostname (full details)
- all_three_present(obj, require_ownership_txt=True) -> bool (CNAME derivable, plus TXT checks)
- build_dns_block(obj, ssl_proxy_url=None) -> str (human "DNS RECORDS TO ADD" block)
- derive_status_from_obj(obj) -> 'pending' | 'generated' | 'applied'
- make_autocf_envelope(domain, obj, status=None, ssl_proxy_url=None) -> dict (DB-ready envelope)
"""

import os
import logging
from typing import Optional, Tuple
from dotenv import load_dotenv
from cloudflare import Cloudflare

# --- Env / client bootstrap (same convention as your scripts) ---
_script_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_script_dir, ".env")
if not os.path.exists(_env_path):
    raise FileNotFoundError(f"env file not found at: {_env_path}")

load_dotenv(dotenv_path=_env_path)

ZONE_ID = os.getenv("CF_ZONE_ID")
TOKEN = os.getenv("CF_TOKEN")
SSL_PROXY_URL_DEFAULT = os.getenv("SSL_PROXY_URL", "ssl-proxy.easydigz.com")

_cf = Cloudflare(api_token=TOKEN)

# Module logger (inherits root config from the app)
logger = logging.getLogger(__name__)


# ---------------- core find/fetch ----------------
def is_apex(domain: str) -> bool:
    return domain.count(".") == 1


def _find_hostname_id(custom_domain: str) -> Optional[str]:
    """Resolve a custom hostname id for a domain. Tries filtered list, full scan, and 'www.' for apex."""
    # 1) filtered
    try:
        resp = _cf.custom_hostnames.list(zone_id=ZONE_ID, params={"hostname": custom_domain})
        items = getattr(resp, "result", resp) or []
        if items:
            return items[0].id
    except Exception:
        pass

    # 2) full list
    try:
        resp = _cf.custom_hostnames.list(zone_id=ZONE_ID)
        items = getattr(resp, "result", resp) or []
        for it in items:
            if getattr(it, "hostname", None) == custom_domain:
                return it.id
    except Exception:
        pass

    # 3) try www. if apex
    if is_apex(custom_domain):
        alt = "www." + custom_domain
        try:
            resp = _cf.custom_hostnames.list(zone_id=ZONE_ID, params={"hostname": alt})
            items = getattr(resp, "result", resp) or []
            if items:
                return items[0].id
        except Exception:
            pass
        try:
            resp = _cf.custom_hostnames.list(zone_id=ZONE_ID)
            items = getattr(resp, "result", resp) or []
            for it in items:
                if getattr(it, "hostname", None) == alt:
                    return it.id
        except Exception:
            pass

    return None


def get_custom_hostname_obj(domain: str):
    """Return the full custom hostname object (with ssl.validation_records), or None if not found."""
    hid = _find_hostname_id(domain.strip().lower())
    if not hid:
        return None
    return _cf.custom_hostnames.get(zone_id=ZONE_ID, custom_hostname_id=hid)


# ---------------- evaluation + formatting ----------------
def all_three_present(obj, require_ownership_txt: bool = True) -> bool:
    """
    True when:
      - Ownership TXT present (unless require_ownership_txt=False), and
      - At least one SSL/ACME TXT present.
    (CNAME is always derivable: name = obj.hostname, value = SSL_PROXY_URL)
    """
    host = getattr(obj, "hostname", "unknown")
    logger.info(
        f"[all_three_present] start host={host} require_ownership_txt={require_ownership_txt}"
    )
    # Ownership
    have_ownership = True
    if require_ownership_txt:
        have_ownership = False
        ov = getattr(obj, "ownership_verification", None)
        ov_type = getattr(ov, "type", None) if ov else None
        ov_has_name = bool(getattr(ov, "name", None)) if ov else False
        ov_has_value = bool(getattr(ov, "value", None)) if ov else False
        if ov and ov_type == "txt" and ov_has_name and ov_has_value:
            have_ownership = True
        logger.info(
            f"[all_three_present] ownership check host={host} ov_type={ov_type} name_present={ov_has_name} value_present={ov_has_value} result={have_ownership}"
        )

    # SSL/ACME
    have_ssl = False
    ssl = getattr(obj, "ssl", None)
    if ssl:
        vrs = getattr(ssl, "validation_records", []) or []
        vr_count = len(vrs)
        vr_with_txt = sum(1 for r in vrs if getattr(r, "txt_name", None) and getattr(r, "txt_value", None))
        direct_txt = hasattr(ssl, "txt_name") and hasattr(ssl, "txt_value")
        have_ssl = (vr_with_txt > 0) or direct_txt
        ssl_status = getattr(ssl, "status", "unknown")
        logger.info(
            f"[all_three_present] ssl check host={host} ssl_status={ssl_status} vr_count={vr_count} vr_with_txt={vr_with_txt} direct_txt={direct_txt} result={have_ssl}"
        )

    result = have_ownership and have_ssl
    logger.info(f"[all_three_present] result host={host} -> {result}")
    return result


def build_dns_block(obj, ssl_proxy_url: Optional[str] = None) -> str:
    """
    Produce the exact human block you store in DB (like autocf.py/checkStatus.py).
    """
    ssl_proxy_url = ssl_proxy_url or SSL_PROXY_URL_DEFAULT
    host = getattr(obj, "hostname", "")
    ver_status = getattr(obj, "status", "unknown")
    ssl = getattr(obj, "ssl", None)
    ssl_status = getattr(ssl, "status", "unknown") if ssl else "unknown"

    lines = []
    lines.append(f"Creating Custom hostname : {host}")
    lines.append(f" Verification Status: {ver_status}")
    lines.append(f" SSL status: {ssl_status}")
    lines.append("")
    lines.append("=== DNS RECORDS TO ADD ===")
    lines.append("")
    lines.append("Please add the following records to your domain's DNS:")
    lines.append("")
    # 1) CNAME (always)
    lines.append("1. CNAME record:")
    lines.append(f"   Name:  {host}")
    lines.append(f"   Value: {ssl_proxy_url}")
    lines.append("")

    printed_txt = False

    # 2) Ownership TXT
    ov = getattr(obj, "ownership_verification", None)
    if ov and getattr(ov, "type", None) == "txt":
        lines.append("2. Ownership Verification TXT:")
        lines.append(f"   Name:  {getattr(ov, 'name', '')}")
        lines.append(f"   Value: {getattr(ov, 'value', '')}")
        lines.append("")
        printed_txt = True

    # 3) SSL/ACME TXT
    if ssl:
        lines.append("3. SSL Validation Records:")
        vrs = getattr(ssl, "validation_records", []) or []
        if vrs:
            for i, r in enumerate(vrs, start=1):
                tn, tv = getattr(r, "txt_name", None), getattr(r, "txt_value", None)
                if tn and tv:
                    lines.append(f"   SSL TXT Record {i} (status: {getattr(r, 'status', 'unknown')}):")
                    lines.append(f"   Name:  {tn}")
                    lines.append(f"   Value: {tv}")
                    lines.append("")
                    printed_txt = True

        if hasattr(ssl, "txt_name") and hasattr(ssl, "txt_value"):
            lines.append("   SSL TXT Record (direct):")
            lines.append(f"   Name:  {getattr(ssl, 'txt_name')}")
            lines.append(f"   Value: {getattr(ssl, 'txt_value')}")
            lines.append("")
            printed_txt = True

        lines.append(f"   SSL Status: {ssl_status}")
        lines.append("")

    if not printed_txt and ssl_status != "active":
        lines.append("   WARNING: SSL validation records not yet available from Cloudflare.")
        lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


def derive_status_from_obj(obj) -> str:
    """
    Map CF object to our statuses:
      - 'applied'   if verification or ssl is active
      - 'generated' if any TXT record is present
      - 'pending'   otherwise
    """
    ssl = getattr(obj, "ssl", None)
    ssl_status = getattr(ssl, "status", "unknown") if ssl else "unknown"
    ver_status = getattr(obj, "status", "unknown")
    if ssl_status == "active" or ver_status == "active":
        return "applied"

    # any TXT?
    if all_three_present(obj, require_ownership_txt=False):  # at least SSL TXT exists
        return "generated"

    return "pending"


def make_autocf_envelope(domain: str, obj, status: Optional[str] = None, ssl_proxy_url: Optional[str] = None) -> dict:
    """
    Build the DB-ready envelope matching your preferred shape.
    """
    stdout_block = build_dns_block(obj, ssl_proxy_url=ssl_proxy_url)
    final_status = status or derive_status_from_obj(obj)
    return {
        "args": [domain],
        "script": "autocf.py",
        "stderr": "",
        "stdout": stdout_block,
        "exit_code": 0,
        "status": final_status,
    }


__all__ = [
    "get_custom_hostname_obj",
    "all_three_present",
    "build_dns_block",
    "derive_status_from_obj",
    "make_autocf_envelope",
    "is_apex",
]
