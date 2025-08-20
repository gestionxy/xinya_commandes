# xinya_app/ui_client.py  (final: single frame + fill image with cover; no st.image)
from typing import Optional, List, Dict, Any
import json
import base64
from pathlib import Path
from datetime import datetime
import html

import streamlit as st

from .config import ADMIN_EMAIL, EMAIL_RE
from .paths import BASE_DIR, ORDERS_DIR, ensure_dir
from .repo_products import load_products
from .ids import gen_order_id

from utils import pdf_utils as _pdf
from utils.image_utils import normalize_image_bytes

# -----------------------
# Helpers
# -----------------------
def _valid_email(s: str) -> bool:
    try:
        return bool(EMAIL_RE.match((s or '').strip()))
    except Exception:
        return False

def _resolve_img_src(image_field: Optional[str]) -> Optional[str]:
    """Return absolute local file path or http(s) url if exists; else None."""
    if not image_field:
        return None
    s = str(image_field).strip()
    if s.startswith(("http://", "https://")):
        return s
    p = Path(s)
    if p.is_file():
        return p.as_posix()
    candidates = [
        BASE_DIR / s,
        BASE_DIR / "assets" / s,
        BASE_DIR / "assets" / "products" / s,
        BASE_DIR / "assets" / "images" / s,
        BASE_DIR / "images" / s,
        BASE_DIR / "static" / "images" / s,
    ]
    for c in candidates:
        if c.is_file():
            return c.as_posix()
    return None

def _to_data_uri(path_or_url: str) -> str:
    """If local path -> return data URI (base64). If URL -> return as-is."""
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    p = Path(path_or_url)
    if p.is_file():
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        ext = p.suffix.lower()
        mime = "image/jpeg"
        if ext == ".png":
            mime = "image/png"
        elif ext == ".webp":
            mime = "image/webp"
        return f"data:{mime};base64,{b64}"
    return ""

def _prepare_img_for_pdf(img_src: Optional[str]) -> Optional[str]:
    """Only local files can be embedded into PDF; ignore remote urls."""
    if not img_src:
        return None
    if img_src.startswith(("http://", "https://")):
        return None
    p = Path(img_src)
    return p.as_posix() if p.is_file() else None

def _init_custom_state():
    if "custom_items" not in st.session_state:
        st.session_state.custom_items = [{
            "name": "",
            "qty_units": 0,
            "qty_cases": 0,
            "remark": "",
            "file": None,
        }]

def _add_custom_row():
    st.session_state.custom_items.append({
        "name": "",
        "qty_units": 0,
        "qty_cases": 0,
        "remark": "",
        "file": None,
    })

def _remove_custom_row(idx: int):
    if 0 <= idx < len(st.session_state.custom_items):
        st.session_state.custom_items.pop(idx)
        if not st.session_state.custom_items:
            _init_custom_state()

# -----------------------
# UI Components
# -----------------------
def _css_once():
    st.markdown("""
    <style>
    /* 单一外框：避免和 st.container(border=True) 叠加产生双框 */
    .xy-card{
      border:1px solid rgba(0,0,0,.08);
      border-radius:16px;
      padding:12px;
      background:#fff;
    }
    .xy-thumb{
      width:100%;
      height:260px;                    /* 画布高度：你已说合适，可按需改 */
      background:#f3f4f6;
      border-radius:12px;
      box-shadow:inset 0 0 0 1px rgba(0,0,0,.05);
      background-repeat:no-repeat;
      background-position:center center;
      background-size:cover;           /* 关键：填满（可能裁一点边） */
      margin-bottom:12px;
    }
    </style>
    """, unsafe_allow_html=True)

def _thumb_div_style(img_src: Optional[str]) -> str:
    if not img_src:
        return ""
    uri = _to_data_uri(img_src)
    if not uri:
        return ""
    return f"background-image:url('{html.escape(uri)}');"

def _render_custom_card(idx: int):
    item = st.session_state.custom_items[idx]
    st.markdown('<div class="xy-card">', unsafe_allow_html=True)
    st.markdown(f"**Personnalisé #{idx+1}**", unsafe_allow_html=True)
    st.text_input("Nom (facultatif)", key=f"c_name_{idx}", value=item["name"])
    fileobj = st.file_uploader("Image (facultatif)", type=["jpg","jpeg","png"], key=f"c_file_{idx}")
    if fileobj is not None:
        st.session_state.custom_items[idx]["file"] = fileobj
    st.text_area("Note (facultatif)", key=f"c_rem_{idx}", value=item["remark"], height=90)
    row = st.columns(2)
    with row[0]:
        st.number_input("Quantité (unités)*", min_value=0, step=1, key=f"c_qtyu_{idx}", value=item["qty_units"])
    with row[1]:
        st.number_input("Quantité (caisses)*", min_value=0, step=1, key=f"c_qtyc_{idx}", value=item["qty_cases"])
    st.markdown('</div>', unsafe_allow_html=True)

# -----------------------
# Page
# -----------------------
def render_client_page():
    st.title("🛒 Xinya Supermarché | Plateforme de commande")
    _css_once()

    # Sidebar (client info)
    with st.sidebar:
        st.header("Client")
        customer_name = st.text_input("Nom *", max_chars=40)
        phone = st.text_input("Téléphone *", max_chars=30)
        email = st.text_input("E-mail *", max_chars=80)
        st.caption(f"Courriel admin : {ADMIN_EMAIL}")

    # Products
    products = load_products()
    departments = ["Tous"] + sorted(set(p.get("department","") for p in products))
    c1, c2, c3 = st.columns([2,1,1])
    with c1:
        q = st.text_input("🔎 Rechercher un produit", "")
    with c2:
        dep = st.selectbox("Département", departments, index=0)
    with c3:
        show_selected_only = st.toggle("Afficher sélectionnés uniquement", False)

    st.subheader("Produits pré-définis")
    filtered = [
        p for p in products
        if (dep == "Tous" or p.get("department","") == dep)
        and (q.lower() in p.get("name","").lower())
    ]
    if show_selected_only:
        filtered = [p for p in filtered if st.session_state.get(f"sel_{p['id']}", False)]

    cols = st.columns(3)
    for i, p in enumerate(filtered):
        col = cols[i % 3]
        with col:
            # 只保留我们自己的外框，避免“双框”
            st.markdown('<div class="xy-card">', unsafe_allow_html=True)

            img_src = _resolve_img_src(p.get("image") or p.get("image_path") or p.get("img"))
            style = _thumb_div_style(img_src)
            st.markdown(f'<div class="xy-thumb" style="{style}"></div>', unsafe_allow_html=True)

            upc = int(p.get("units_per_case", 0) or 0)
            st.caption(f"Unité / caisse：{upc or '—'}")

            sel_key  = f"sel_{p['id']}"
            qtyu_key = f"qtyu_{p['id']}"
            qtyc_key = f"qtyc_{p['id']}"
            rem_key  = f"rem_{p['id']}"

            row1 = st.columns([1,1,1])
            with row1[0]:
                selected = st.checkbox("Choisir", key=sel_key)
            prev_u = st.session_state.get(qtyu_key, 0)
            prev_c = st.session_state.get(qtyc_key, 0)
            if selected and (prev_u == 0 and prev_c == 0):
                prev_u = 1
            with row1[1]:
                st.number_input("Unités", min_value=0, step=1, value=prev_u, key=qtyu_key)
            with row1[2]:
                st.number_input("Caisses", min_value=0, step=1, value=prev_c, key=qtyc_key)

            st.text_area("Remarque", key=rem_key, height=60,
                         placeholder="Option : découpe / emballage / goût…")

            st.markdown('</div>', unsafe_allow_html=True)

    # ---------- Custom products ----------
    st.subheader("Produits personnalisés (image OU note + quantité)")
    _init_custom_state()
    items = st.session_state.custom_items

    # Render in rows of 3
    idx = 0
    while idx < len(items) or True:
        cols = st.columns(3)
        for c in range(3):
            with cols[c]:
                if idx < len(items):
                    _render_custom_card(idx)
                    idx += 1
                else:
                    if st.button("➕ Ajouter", key=f"add_custom_{idx}", use_container_width=True):
                        _add_custom_row()
                    idx += 1
                    break
        if idx >= len(items) + 1:
            break

    # ---------- Submit ----------
    st.markdown("---")
    submit = st.button("✅ Soumettre la commande", type="primary", use_container_width=True)
    if not submit:
        return

    if not customer_name or not phone or not _valid_email(email):
        st.error("请填写：姓名、电话、有效邮箱。")
        return

    order_id = gen_order_id(customer_name)
    order_folder = ensure_dir(ORDERS_DIR / order_id)

    chosen: List[Dict[str, Any]] = []
    for p in products:
        pid = p["id"]
        if st.session_state.get(f"sel_{pid}", False):
            q_u = int(st.session_state.get(f"qtyu_{pid}", 0) or 0)
            q_c = int(st.session_state.get(f"qtyc_{pid}", 0) or 0)
            if q_u == 0 and q_c == 0:
                continue
            img_src = _resolve_img_src(p.get("image") or p.get("image_path") or p.get("img"))
            chosen.append({
                "name": p.get("name", ""),
                "qty_units": q_u,
                "qty_cases": q_c,
                "units_per_case": int(p.get("units_per_case", 0) or 0),
                "remark": st.session_state.get(f"rem_{pid}", ""),
                "image_path": _prepare_img_for_pdf(img_src),
            })

    # custom items
    for i, it in enumerate(st.session_state.custom_items):
        q_u = int(st.session_state.get(f"c_qtyu_{i}", it["qty_units"]) or 0)
        q_c = int(st.session_state.get(f"c_qtyc_{i}", it["qty_cases"]) or 0)
        name = st.session_state.get(f"c_name_{i}", it["name"]).strip()
        remark = st.session_state.get(f"c_rem_{i}", it["remark"]).strip()
        fileobj = st.session_state.get(f"c_file_{i}", it["file"])

        has_qty = (q_u > 0 or q_c > 0)
        has_content = bool(fileobj) or bool(remark)
        if not (has_qty and has_content):
            continue

        img_path = None
        if fileobj:
            try:
                norm = normalize_image_bytes(fileobj.getvalue())
                img_name = f"custom_{order_id}_{str(i).zfill(2)}.jpg"
                out_path = order_folder / img_name
                with open(out_path, "wb") as f:
                    f.write(norm)
                img_path = out_path.as_posix()
            except Exception:
                img_path = None

        chosen.append({
            "name": name or f"Personnalisé #{i+1}",
            "qty_units": q_u,
            "qty_cases": q_c,
            "units_per_case": 0,
            "remark": remark,
            "image_path": img_path,
        })

    if not chosen:
        st.warning("请选择至少一个商品（或添加自选商品）并填写数量。")
        return

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    order_data = {
        "order_id": order_id,
        "customer_name": customer_name,
        "phone": phone,
        "email": email,
        "created_at": created_at,
        "items": chosen,
    }

    pdf_path = order_folder / f"Commande_{order_id}.pdf"
    try:
        _pdf.build_order_pdf_table(order_data, str(pdf_path))
    except Exception as e:
        st.error(f"PDF 生成失败：{e}")
        return

    try:
        (order_folder / "order.json").write_text(
            json.dumps(order_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        st.warning(f"保存 order.json 失败：{e}")

    with open(pdf_path, "rb") as f:
        st.download_button("📄 Télécharger le PDF", data=f.read(),
                           file_name=pdf_path.name, mime="application/pdf")

    st.info(f"ID de commande : **{order_id}**")
