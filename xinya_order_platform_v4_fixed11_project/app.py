
import streamlit as st
from xinya_app.config import email_config_ok
from xinya_app.ids import fix_duplicate_product_ids_file
from xinya_app.ui_client import render_client_page
from xinya_app.ui_admin import render_admin_page

st.set_page_config(page_title="Xinya | Commandes", layout="wide")

tab = st.sidebar.radio("Pages", ["Commander", "Admin"], index=0)

changed, cnt = fix_duplicate_product_ids_file()
if changed:
    st.sidebar.warning(f"⚠️ IDs produits dupliqués corrigés automatiquement：{cnt} modifiés.")

if not email_config_ok():
    st.sidebar.warning("⚠️ Envoi d'e-mails non configuré. Copiez `.env.example` → `.env`, remplissez EMAIL_USER et EMAIL_PASS.")
else:
    st.sidebar.success("📧 E-mails configurés.")

if tab == "Commander":
    render_client_page()
else:
    render_admin_page()
