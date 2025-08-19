# xinya_app/ui_client.py
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd

from .config import ADMIN_EMAIL, EMAIL_RE, email_config_ok
from .paths import BASE_DIR, ORDERS_DIR, ensure_dir
from .repo_products import load_products
from .ids import gen_order_id

# 仅保留新的 PDF 生成器，避免与旧版混用
from utils import pdf_utils as _pdf
from utils.image_utils import normalize_image_bytes
from utils.storage_github import GitHubStorage

# -----------------------
# 小工具
# -----------------------
def _valid_email(s: str) -> bool:
    try:
        return bool(EMAIL_RE.match((s or "").strip()))
    except Exception:
        return False

def _units_total(q_units: int, q_cases: int, upc: int) -> int:
    q_units = int(q_units or 0)
    q_cases = int(q_cases or 0)
    upc = int(upc or 0)
    return q_units + q_cases * upc

def _init_custom_state():
    if "custom_items" not in st.session_state:
        # 每个自选项结构：{"name","qty_units","qty_cases","units_per_case","remark","file"}（file=UploadedFile或None）
        st.session_state.custom_items = [{"name": "", "qty_units": 0, "qty_cases": 0,
                                          "units_per_case": 0, "remark": "", "file": None}]

def _add_custom_row():
    st.session_state.custom_items.append({"name": "", "qty_units": 0, "qty_cases": 0,
                                          "units_per_case": 0, "remark": "", "file": None})

def _remove_custom_row(idx: int):
    if 0 <= idx < len(st.session_state.custom_items):
        st.session_state.custom_items.pop(idx)
        if not st.session_state.custom_items:
            _init_custom_state()

# -----------------------
# 页面主体
# -----------------------
def render_client_page():
    st.title("🛒 Xinya Supermarché | Plateforme de commande")

    # —— 客户信息（侧栏）
    with st.sidebar:
        st.header("Client")
        customer_name = st.text_input("Nom *", max_chars=40)
        phone = st.text_input("Téléphone *", max_chars=30)
        email = st.text_input("E-mail *", max_chars=80)
        st.markdown(f"**Courriel admin** : `{ADMIN_EMAIL}`")

    # —— 预设商品
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
        and (q.lower() in (p.get("name","").lower()))
    ]

    if show_selected_only:
        filtered = [p for p in filtered if st.session_state.get(f"sel_{p['id']}", False)]

    # 三列卡片展示
    cols = st.columns(3, vertical_alignment="top")
    for i, p in enumerate(filtered):
        col = cols[i % 3]
        with col:
            with st.container(border=True):
                # 预览图
                try:
                    img_path = (BASE_DIR / p["image"]).as_posix()
                    st.image(img_path, use_container_width=True)
                except Exception:
                    st.write("🖼️ (image introuvable)")

                upc = int(p.get("units_per_case", 0) or 0)
                st.caption(f"Unité / caisse：{upc or '—'}")

                sel_key = f"sel_{p['id']}"
                qtyu_key = f"qtyu_{p['id']}"
                qtyc_key = f"qtyc_{p['id']}"
                rem_key = f"rem_{p['id']}"

                row1 = st.columns([1, 1, 1])
                with row1[0]:
                    selected = st.checkbox("Choisir", key=sel_key)
                # 默认：勾选后给 1 件，避免“0 选择”
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

    # —— 自选商品
    st.subheader("Produits personnalisés（图片 或 备注 + 数量）")
    _init_custom_state()
    for idx, item in enumerate(st.session_state.custom_items):
        with st.container(border=True):
            top = st.columns([6, 1])
            with top[0]:
                st.text_input("Nom du produit", key=f"c_name_{idx}", value=item["name"],
                              on_change=lambda i=idx: _sync_custom_text(i, "name"))
            with top[1]:
                st.button("Retirer", key=f"c_rm_{idx}", on_click=_remove_custom_row, args=(idx,))

            row = st.columns([1, 1, 1, 1])
            with row[0]:
                st.number_input("Unités", min_value=0, step=1, key=f"c_qtyu_{idx}", value=item["qty_units"],
                                on_change=lambda i=idx: _sync_custom_num(i, "qty_units"))
            with row[1]:
                st.number_input("Caisses", min_value=0, step=1, key=f"c_qtyc_{idx}", value=item["qty_cases"],
                                on_change=lambda i=idx: _sync_custom_num(i, "qty_cases"))
            with row[2]:
                st.number_input("Unités / caisse", min_value=0, step=1, key=f"c_upc_{idx}", value=item["units_per_case"],
                                on_change=lambda i=idx: _sync_custom_num(i, "units_per_case"))
            with row[3]:
                st.file_uploader("Image (optionnel)", type=["jpg", "jpeg", "png"], key=f"c_file_{idx}",
                                 on_change=lambda i=idx: _sync_custom_file(i))

            st.text_area("Remarque", key=f"c_rem_{idx}", value=item["remark"], height=60,
                         on_change=lambda i=idx: _sync_custom_text(i, "remark"))

    st.button("➕ Ajouter un produit personnalisé", on_click=_add_custom_row)

    # —— 提交
    st.markdown("---")
    submit = st.button("✅ Soumettre la commande", type="primary", use_container_width=True)
    if not submit:
        return

    # 校验
    if not customer_name or not phone or not _valid_email(email):
        st.error("请填写：姓名、电话、有效邮箱。")
        return

    # 收集选中的预设项
    chosen = []
    for p in products:
        pid = p["id"]
        if st.session_state.get(f"sel_{pid}", False):
            q_u = int(st.session_state.get(f"qtyu_{pid}", 0) or 0)
            q_c = int(st.session_state.get(f"qtyc_{pid}", 0) or 0)
            if q_u == 0 and q_c == 0:
                continue
            item = {
                "name": p.get("name", ""),
                "qty_units": q_u,
                "qty_cases": q_c,
                "units_per_case": int(p.get("units_per_case", 0) or 0),
                "remark": st.session_state.get(f"rem_{pid}", ""),
                "image_path": (BASE_DIR / p.get("image","")).as_posix() if p.get("image") else None,
            }
            chosen.append(item)

    # 收集自选项（必须满足：图片或备注之一 + 有数量）
    for idx, item in enumerate(st.session_state.custom_items):
        q_u = int(item.get("qty_units", 0) or int(st.session_state.get(f"c_qtyu_{idx}", 0) or 0))
        q_c = int(item.get("qty_cases", 0) or int(st.session_state.get(f"c_qtyc_{idx}", 0) or 0))
        name = (item.get("name") or st.session_state.get(f"c_name_{idx}", "")).strip()
        upc = int(item.get("units_per_case", 0) or int(st.session_state.get(f"c_upc_{idx}", 0) or 0))
        remark = (item.get("remark") or st.session_state.get(f"c_rem_{idx}", "")).strip()
        fileobj = st.session_state.get(f"c_file_{idx}")  # UploadedFile or None

        has_qty = (q_u > 0 or q_c > 0)
        has_content = bool(fileobj) or bool(remark)
        if not (has_qty and has_content):
            continue

        chosen.append({
            "name": name or f"Personnalisé #{idx+1}",
            "qty_units": q_u,
            "qty_cases": q_c,
            "units_per_case": upc,
            "remark": remark,
            # 图片路径稍后在落盘时补齐
            "image_path": None,
            "_upload_idx": idx,  # 临时字段，后面存盘用
        })

    if not chosen:
        st.warning("请选择至少一个商品（或添加自选商品）并填写数量。")
        return

    # —— 生成订单文件夹
    order_id = gen_order_id(customer_name)
    order_folder = ensure_dir(ORDERS_DIR / order_id)

    # 将自选图片落盘到订单目录，并补齐 image_path
    for it in chosen:
        if "_upload_idx" in it:
            idx = it.pop("_upload_idx")
            fileobj = st.session_state.get(f"c_file_{idx}")
            if fileobj:
                try:
                    norm = normalize_image_bytes(fileobj.getvalue())
                    img_name = f"custom_{order_id}_{idx:02d}.jpg"
                    img_path = order_folder / img_name
                    with open(img_path, "wb") as f:
                        f.write(norm)
                    it["image_path"] = img_path.as_posix()
                except Exception:
                    it["image_path"] = None

    # —— 组装 order_data
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    order_data = {
        "order_id": order_id,
        "customer_name": customer_name,
        "phone": phone,
        "email": email,
        "created_at": created_at,
        "items": chosen,
    }

    # —— 生成 PDF（四列表格版）
    pdf_path = order_folder / f"Commande_{order_id}.pdf"
    try:
        _pdf.build_order_pdf_table(order_data, str(pdf_path))
    except Exception as e:
        st.error(f"PDF 生成失败：{e}")
        return

    # 保存 metadata
    try:
        (order_folder / "order.json").write_text(
            json.dumps(order_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        st.warning(f"保存 order.json 失败：{e}")

    # —— 邮件发送
    subject = f"Xinya_Commandes_{order_id}"
    body = f"Bonjour {customer_name},\n\nVotre commande est créée (ID: {order_id}). Le PDF est en pièce jointe."
    try:
        # 用 utils.email_utils 下的实现（经 services_email 简转）
        from utils import email_utils as _email
        to_list = [ADMIN_EMAIL]
        if _valid_email(email):
            to_list.append(email)
        _email.send_email_with_attachment(subject, body, to_list, [str(pdf_path)])
        st.success("✅ Commande envoyée ! Le PDF a été expédié à l'admin et au client.")
    except Exception as e:
        st.warning(f"⚠️ L'e-mail n'a pas été envoyé : {e}\nLe PDF a été生成在本地。")

    # —— GitHub 备份（可选）
    try:
        se = st.secrets
        token = se["GITHUB_TOKEN"]
        repo = se["GITHUB_REPO"]
        branch = se.get("GITHUB_BRANCH", "main")
        base_path = se.get("GITHUB_BASE_PATH", "").strip()
        storage = GitHubStorage(token=token, repo=repo, branch=branch, base_path=base_path)

        remote_dir = f"{order_id}"
        with open(pdf_path, "rb") as f:
            storage.upload_bytes(f"{remote_dir}/Commande_{order_id}.pdf", f.read(),
                                 commit_message=f"order {order_id}: add pdf")
        meta_bytes = json.dumps(order_data, ensure_ascii=False, indent=2).encode("utf-8")
        storage.upload_bytes(f"{remote_dir}/order.json", meta_bytes,
                             commit_message=f"order {order_id}: add metadata")
        st.success("☁️ 已将订单备份到 GitHub。")
    except Exception as e:
        st.info(f"（可选）GitHub 备份未完成：{e}")

    # —— 下载按钮 + 提示
    with open(pdf_path, "rb") as f:
        st.download_button("📄 Télécharger le PDF",
                           data=f.read(),
                           file_name=pdf_path.name,
                           mime="application/pdf")
    st.info(f"ID de commande : **{order_id}**")


# -----------------------
# 自选项字段同步（回写到 session_state.custom_items）
# -----------------------
def _sync_custom_text(i: int, field: str):
    if "custom_items" not in st.session_state:
        return
    key = f"c_{'name' if field=='name' else 'rem'}_{i}" if field in ("name","remark") else ""
    if key:
        st.session_state.custom_items[i][field] = st.session_state.get(key, "")

def _sync_custom_num(i: int, field: str):
    if "custom_items" not in st.session_state:
        return
    key = f"c_qtyu_{i}" if field == "qty_units" else \
          f"c_qtyc_{i}" if field == "qty_cases" else \
          f"c_upc_{i}"
    st.session_state.custom_items[i][field] = int(st.session_state.get(key, 0) or 0)

def _sync_custom_file(i: int):
    if "custom_items" not in st.session_state:
        return
    key = f"c_file_{i}"
    st.session_state.custom_items[i]["file"] = st.session_state.get(key)
