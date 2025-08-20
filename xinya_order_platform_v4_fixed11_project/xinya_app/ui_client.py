# xinya_app/ui_client.py
from typing import Optional
import json
from pathlib import Path
from datetime import datetime

import streamlit as st

from .config import ADMIN_EMAIL, EMAIL_RE, email_config_ok
from .paths import BASE_DIR, ORDERS_DIR, ensure_dir
from .repo_products import load_products
from .ids import gen_order_id

from utils import pdf_utils as _pdf
from utils.image_utils import normalize_image_bytes
from utils.storage_github import GitHubStorage

# -----------------------
# Helpers
# -----------------------
def _valid_email(s: str) -> bool:
    try:
        return bool(EMAIL_RE.match((s or '').strip()))
    except Exception:
        return False

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

def _resolve_img_src(image_field: Optional[str]) -> Optional[str]:
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
        BASE_DIR / "assets" / "images" / s,
        BASE_DIR / "images" / s,
        BASE_DIR / "static" / "images" / s,
    ]
    for c in candidates:
        if c.is_file():
            return c.as_posix()
    return None

def _prepare_img_for_pdf(img_src: Optional[str]) -> Optional[str]:
    if not img_src:
        return None
    if img_src.startswith(("http://", "https://")):
        return None
    p = Path(img_src)
    return p.as_posix() if p.is_file() else None

# -----------------------
# Page
# -----------------------
def render_client_page():
    st.title("🛒 Xinya Supermarché | Plateforme de commande")

    # Sidebar
    with st.sidebar:
        st.header("Client")
        customer_name = st.text_input("Nom *", max_chars=40)
        phone = st.text_input("Téléphone *", max_chars=30)
        email = st.text_input("E-mail *", max_chars=80)
        st.markdown("**Courriel admin** : `{}`".format(ADMIN_EMAIL))

    # Products
    products = load_products()
    departments = ["Tous"] + sorted(set(p.get("department", "") for p in products))
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        q = st.text_input("🔎 Rechercher un produit", "")
    with c2:
        dep = st.selectbox("Département", departments, index=0)
    with c3:
        show_selected_only = st.toggle("Afficher sélectionnés uniquement", False)

    st.subheader("Produits pré-définis")
    filtered = [
        p for p in products
        if (dep == "Tous" or p.get("department", "") == dep)
        and (q.lower() in (p.get("name", "").lower()))
    ]
    if show_selected_only:
        filtered = [p for p in filtered if st.session_state.get("sel_{}".format(p["id"]), False)]

    cols = st.columns(3)
    for i, p in enumerate(filtered):
        col = cols[i % 3]
        with col:
            with st.container(border=True):
                img_src = _resolve_img_src(p.get("image") or p.get("image_path") or p.get("img"))
                if img_src:
                    st.image(img_src, use_column_width=True)
                else:
                    st.write("🖼️ (image introuvable)")

                upc = int(p.get("units_per_case", 0) or 0)
                st.caption("Unité / caisse：{}".format(upc or "—"))

                sel_key = "sel_{}".format(p["id"])
                qtyu_key = "qtyu_{}".format(p["id"])
                qtyc_key = "qtyc_{}".format(p["id"])
                rem_key = "rem_{}".format(p["id"])

                row1 = st.columns([1, 1, 1])
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

    # ---------- Custom products: 3-column grid ----------
    st.subheader("Produits personnalisés (image OU note + quantité)")

    _init_custom_state()
    items = st.session_state.custom_items
    plus_rendered = False
    start = 0
    while True:
        cols = st.columns(3)
        # Fill three slots per row
        for pos in range(3):
            col = cols[pos]
            idx = start + pos
            if idx < len(items):
                _render_custom_card(col, idx)
            elif not plus_rendered:
                with col:
                    st.container(border=True)
                    st.button("➕ Ajouter", on_click=_add_custom_row, use_container_width=True, key=f"add_row_{start}")
                plus_rendered = True
            else:
                # empty slot
                with col:
                    st.write("")
        start += 3
        if start >= len(items) and plus_rendered:
            break
        if start >= len(items) and not plus_rendered:
            # still need to render a row to place plus
            continue

    # Submit
    st.markdown("---")
    submit = st.button("✅ Soumettre la commande", type="primary", use_container_width=True)
    if not submit:
        return

    if not customer_name or not phone or not _valid_email(email):
        st.error("请填写：姓名、电话、有效邮箱。")
        return

    order_id = gen_order_id(customer_name)
    order_folder = ensure_dir(ORDERS_DIR / order_id)

    chosen = []
    for p in products:
        pid = p["id"]
        if st.session_state.get("sel_{}".format(pid), False):
            q_u = int(st.session_state.get("qtyu_{}".format(pid), 0) or 0)
            q_c = int(st.session_state.get("qtyc_{}".format(pid), 0) or 0)
            if q_u == 0 and q_c == 0:
                continue
            img_src = _resolve_img_src(p.get("image") or p.get("image_path") or p.get("img"))
            item = {
                "name": p.get("name", ""),
                "qty_units": q_u,
                "qty_cases": q_c,
                "units_per_case": int(p.get("units_per_case", 0) or 0),
                "remark": st.session_state.get("rem_{}".format(pid), ""),
                "image_path": _prepare_img_for_pdf(img_src),
            }
            chosen.append(item)

    # Custom items: NO 'units_per_case' field; fix to 0
    for idx, item in enumerate(st.session_state.custom_items):
        q_u = int(item.get("qty_units", 0) or int(st.session_state.get("c_qtyu_{}".format(idx), 0) or 0))
        q_c = int(item.get("qty_cases", 0) or int(st.session_state.get("c_qtyc_{}".format(idx), 0) or 0))
        name = (item.get("name") or st.session_state.get("c_name_{}".format(idx), "")).strip()
        remark = (item.get("remark") or st.session_state.get("c_rem_{}".format(idx), "")).strip()
        fileobj = st.session_state.get("c_file_{}".format(idx))

        has_qty = (q_u > 0 or q_c > 0)
        has_content = bool(fileobj) or bool(remark)
        if not (has_qty and has_content):
            continue

        img_path = None
        if fileobj:
            try:
                norm = normalize_image_bytes(fileobj.getvalue())
                img_name = "custom_{}_{}.jpg".format(order_id, str(idx).zfill(2))
                out_path = order_folder / img_name
                with open(out_path, "wb") as f:
                    f.write(norm)
                img_path = out_path.as_posix()
            except Exception:
                img_path = None

        chosen.append({
            "name": name or "Personnalisé #{}".format(idx+1),
            "qty_units": q_u,
            "qty_cases": q_c,
            "units_per_case": 0,  # removed from UI; set to 0
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

    pdf_path = order_folder / "Commande_{}.pdf".format(order_id)
    try:
        _pdf.build_order_pdf_table(order_data, str(pdf_path))
    except Exception as e:
        st.error("PDF 生成失败：{}".format(e))
        return

    try:
        (order_folder / "order.json").write_text(
            json.dumps(order_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        st.warning("保存 order.json 失败：{}".format(e))

    subject = "Xinya_Commandes_{}".format(order_id)
    body = "Bonjour {},\n\nVotre commande est créée (ID: {}). Le PDF est en pièce jointe.".format(customer_name, order_id)
    try:
        try:
            from utils import email_utils as _email
            to_list = [ADMIN_EMAIL]
            if _valid_email(email):
                to_list.append(email)
            _email.send_email_with_attachment(subject, body, to_list, [str(pdf_path)])
        except Exception:
            from .services_email import send_email_with_attachment as legacy_send
            to_list = [ADMIN_EMAIL]
            if _valid_email(email):
                to_list.append(email)
            legacy_send(subject, body, to_list, [str(pdf_path)])
        st.success("✅ Commande envoyée ! Le PDF a été expédié à l'admin et au client.")
    except Exception as e:
        st.warning("⚠️ L'e-mail n'a不是被发送：{}\nPDF 已生成在本地。".format(e))

    try:
        se = st.secrets
        token = se["GITHUB_TOKEN"]
        repo = se["GITHUB_REPO"]
        branch = se.get("GITHUB_BRANCH", "main")
        base_path = se.get("GITHUB_BASE_PATH", "").strip()
        storage = GitHubStorage(token=token, repo=repo, branch=branch, base_path=base_path)

        remote_dir = "{}".format(order_id)
        with open(pdf_path, "rb") as f:
            storage.upload_bytes("{}/Commande_{}.pdf".format(remote_dir, order_id), f.read(),
                                 commit_message="order {}: add pdf".format(order_id))
        import json as _json
        meta_bytes = _json.dumps(order_data, ensure_ascii=False, indent=2).encode("utf-8")
        storage.upload_bytes("{}/order.json".format(remote_dir), meta_bytes,
                             commit_message="order {}: add metadata".format(order_id))
        st.success("☁️ 已将订单备份到 GitHub。")
    except Exception as e:
        st.info("（可选）GitHub 备份未完成：{}".format(e))

    with open(pdf_path, "rb") as f:
        st.download_button("📄 Télécharger le PDF",
                           data=f.read(),
                           file_name=pdf_path.name,
                           mime="application/pdf")
    st.info("ID de commande : **{}**".format(order_id))


def _render_custom_card(col, idx: int):
    item = st.session_state.custom_items[idx]
    with col:
        with st.container(border=True):
            top = st.columns([5, 1])
            with top[0]:
                st.markdown("**Personnalisé #{}**".format(idx+1))
            with top[1]:
                st.button("Retirer", key="c_rm_{}".format(idx),
                          on_click=_remove_custom_row, args=(idx,))

            st.text_input("Nom (facultatif) #{}".format(idx+1),
                          key="c_name_{}".format(idx), value=item["name"],
                          on_change=lambda i=idx: _sync_custom_text(i, "name"))

            st.file_uploader("Image (facultatif) #{}".format(idx+1),
                             type=["jpg", "jpeg", "png"],
                             key="c_file_{}".format(idx),
                             on_change=lambda i=idx: _sync_custom_file(i))

            st.text_area("Note (facultatif) #{}".format(idx+1),
                         key="c_rem_{}".format(idx), value=item["remark"], height=90,
                         on_change=lambda i=idx: _sync_custom_text(i, "remark"))

            row = st.columns(2)
            with row[0]:
                st.number_input("Quantité (unités) * #{}".format(idx+1),
                                min_value=0, step=1,
                                key="c_qtyu_{}".format(idx), value=item["qty_units"],
                                on_change=lambda i=idx: _sync_custom_num(i, "qty_units"))
            with row[1]:
                st.number_input("Quantité (caisses) * #{}".format(idx+1),
                                min_value=0, step=1,
                                key="c_qtyc_{}".format(idx), value=item["qty_cases"],
                                on_change=lambda i=idx: _sync_custom_num(i, "qty_cases"))

# -----------------------
# State sync
# -----------------------
def _sync_custom_text(i: int, field: str):
    if "custom_items" not in st.session_state:
        return
    if field == "name":
        key = "c_name_{}".format(i)
    else:
        key = "c_rem_{}".format(i)
    st.session_state.custom_items[i][field] = st.session_state.get(key, "")

def _sync_custom_num(i: int, field: str):
    if "custom_items" not in st.session_state:
        return
    if field == "qty_units":
        key = "c_qtyu_{}".format(i)
    elif field == "qty_cases":
        key = "c_qtyc_{}".format(i)
    else:
        key = "c_qtyu_{}".format(i)  # never used
    st.session_state.custom_items[i][field] = int(st.session_state.get(key, 0) or 0)

def _sync_custom_file(i: int):
    if "custom_items" not in st.session_state:
        return
    key = "c_file_{}".format(i)
    st.session_state.custom_items[i]["file"] = st.session_state.get(key)
