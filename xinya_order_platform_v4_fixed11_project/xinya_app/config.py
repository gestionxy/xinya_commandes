
import os, re
from dotenv import load_dotenv
try:
    import streamlit as st
    _SECRETS = dict(st.secrets) if hasattr(st, "secrets") else {}
except Exception:
    _SECRETS = {}
def _get(name, default=None):
    return _SECRETS.get(name, os.getenv(name, default))
load_dotenv(override=True)
ADMIN_EMAIL = _get("ADMIN_EMAIL", "information.xinya@gmail.com")
ADMIN_PASS  = _get("ADMIN_PASS", "admin123")
EMAIL_HOST = _get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(_get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = str(_get("EMAIL_USE_TLS", "true")).lower() == "true"
EMAIL_USER = _get("EMAIL_USER")
EMAIL_PASS = _get("EMAIL_PASS")
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
def email_config_ok() -> bool:
    return bool(EMAIL_USER) and bool(EMAIL_PASS)
