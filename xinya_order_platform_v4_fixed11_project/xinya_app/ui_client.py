# xinya_app/ui_client.py (replacement)
from typing import Optional, List, Dict, Any
import json
from pathlib import Path
from datetime import datetime

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
    """Return a file path (string) or http(s) url that exists, else None."""
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
    .product-card{border:1px solid rgba(0,0,0,.06);border-radius:12px;padding:12px;}
    .product-thumb{
      width:100%;
      height:220px;
      background:#f3f4f6;
      border-radius:12px;
      box-shadow:inset 0 0 0 1px rgba(0,0,0,.05);
      overflow:hidden;
      display:flex;align-items:center;justify-content:center;
      margin-bottom:8px;
    }
    /* force st.image <img> inside our thumb to fill and keep aspect */
    .product-thumb img{
      width:100% !important;
      height:100% !important;
      max-width:none !important;
      object-fit:contain !important;   /* keep aspect, no crop */
      object-position:center center !important;
      display:block;
    }
    </style>
    """, unsafe_allow_html=True)

def _image_in_thumb(img_src: Optional[str]):
    st.markdown('<div class="product-thumb">', unsafe_allow_html=True)
    if img_src:
        # Use Streamlit's image so local files are served; CSS above fixes sizing.
        try:
            st.image(img_src, use_container_width=True)
        except TypeError:
            st.image(img_src, use_column_width=True)
    else:
        st.write("🖼️")
    st.markdown('</div>', unsafe_allow_html=True)

def _render_custom_card(idx: int):
    item = st.session_state.custom_items[idx]
    with st.container(border=True):
        top = st.columns([5,1])
        with top[0]:
            st.markdown(f"**Personnalisé #{idx+1}**")
        with top[1]:
            st.button("Retirer", key=f"c_rm_{idx}", on_click=_remove_custom_row, args=(idx,))
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
            with st.container(border=True):
                st.markdown('<div class="product-card">', unsafe_allow_html=True)

                img_src = _resolve_img_src(p.get("image") or p.get("image_path") or p.get("img"))
                _image_in_thumb(img_src)

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

    # email (best-effort; keep silent if not configured)
    try:
        from utils import email_utils as _email
        to_list = [ADMIN_EMAIL]
        if _valid_email(email):
            to_list.append(email)
        subject = f"Xinya_Commandes_{order_id}"
        body = f"Bonjour {customer_name},\\n\\nVotre commande est créée (ID: {order_id}). Le PDF est en pièce jointe."
        _email.send_email_with_attachment(subject, body, to_list, [str(pdf_path)])
        st.success("✅ Commande envoyée ! Le PDF a été expédié à l'admin et au client.")
    except Exception as e:
        st.info(f"（提示）邮件未发送：{e}")

    # download
    with open(pdf_path, "rb") as f:
        st.download_button("📄 Télécharger le PDF", data=f.read(),
                           file_name=pdf_path.name, mime="application/pdf")

    st.info(f"ID de commande : **{order_id}**")
