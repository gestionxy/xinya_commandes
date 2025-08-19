import os, io, json, zipfile, uuid, re
from pathlib import Path
from datetime import datetime, date
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from utils.pdf_utils import build_order_pdf
from utils.email_utils import send_email_with_attachment

# ---------------------- Config & constants ----------------------

# Email validation (fixed)
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

load_dotenv(override=True)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
PRODUCTS_DIR = ASSETS_DIR / "products"
ORDERS_DIR = BASE_DIR / "orders"

st.set_page_config(page_title="Xinya | Commandes", layout="wide")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "wanghy.gestionxy@gmail.com")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")

PRODUCTS_JSON = DATA_DIR / "products.json"


# ---------------------- Helpers ----------------------

def ts_now():
    return datetime.now().strftime("%Y%m%d%H%M%S")


def gen_order_id(customer_name: str):
    clean = re.sub(r"\s+", "", customer_name or "").strip()
    return f"{clean}_{ts_now()}"


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)
    return p


def email_config_ok():
    return bool(os.getenv("EMAIL_USER")) and bool(os.getenv("EMAIL_PASS"))


def _make_unique_pid(existing: set):
    """Generate globally-unique product id."""
    import uuid as _uuid
    from datetime import datetime as _dt
    while True:
        # microsecond + random 4 => practically unique
        new_id = "p" + _dt.now().strftime("%Y%m%d%H%M%S_%f") + "_" + _uuid.uuid4().hex[:4]
        if new_id not in existing:
            return new_id


def _fix_duplicate_product_ids_file():
    """Scan data/products.json and rewrite if duplicate IDs are found."""
    try:
        p = PRODUCTS_JSON
        if not p.exists():
            return False, 0
        import json as _json
        data = _json.loads(p.read_text(encoding="utf-8"))
        seen = set()
        changed = False
        count = 0
        for prod in data:
            pid = str(prod.get("id", "")).strip()
            if not pid or pid in seen:
                pid = _make_unique_pid(seen)
                prod["id"] = pid
                changed = True
                count += 1
            seen.add(pid)
        if changed:
            p.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return changed, count
    except Exception:
        return False, 0


@st.cache_data
def load_products():
    if not PRODUCTS_JSON.exists():
        return []
    data = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
    for p in data:
        if "department" not in p and "category" in p:
            p["department"] = p["category"]
        if "unit_price" not in p and "price" in p:
            p["unit_price"] = p["price"]
        if "units_per_case" not in p:
            p["units_per_case"] = 12
    return data


def save_products(data):
    PRODUCTS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    load_products.clear()


def count_items_and_qty(items):
    total_units = 0
    for i in items:
        total_units += int(i.get("qty_units", 0) or 0) + int(i.get("qty_cases", 0) or 0) * int(i.get("units_per_case", 0) or 0)
    return len(items), total_units


# ---------------------- UI: Sidebar & bootstrap ----------------------

tab = st.sidebar.radio("Pages", ["Commander", "Admin"], index=0)

# Auto-fix duplicate product IDs at startup
changed_dups, dups_cnt = _fix_duplicate_product_ids_file()
if changed_dups:
    st.sidebar.warning(f"⚠️ IDs produits dupliqués corrigés automatiquement：{dups_cnt} modifiés.")

if not email_config_ok():
    st.sidebar.warning("⚠️ Envoi d'e-mails non configuré. Copiez `.env.example` → `.env`, remplissez EMAIL_USER et EMAIL_PASS.")
else:
    st.sidebar.success("📧 E-mails configurés.")


# ===================== Commander (Client) =====================
if tab == "Commander":
    st.title("🛒 Xinya Supermarché | Plateforme de commande")

    with st.sidebar:
        st.header("Client")
        name = st.text_input("Nom *", max_chars=40, placeholder="Ex. M. Wang / Xiaoming Wang")
        phone = st.text_input("Téléphone *", max_chars=30, placeholder="Mobile ou fixe")
        email = st.text_input("E-mail *", max_chars=80, placeholder="Ex. name@example.com")
        st.markdown(f"**Courriel admin** : `{ADMIN_EMAIL}`")

    products = load_products()
    departments = sorted(set(p.get("department", "") for p in products))

    col_search, col_dep, col_sel_only = st.columns([2, 1, 1])
    with col_search:
        q = st.text_input("🔎 Rechercher un produit", value="", placeholder="Ex. Salmon / Apple / Dumplings")
    with col_dep:
        dep = st.selectbox("Département", options=["Tous"] + departments, index=0)
    with col_sel_only:
        show_selected_only = st.toggle("Afficher sélectionnés uniquement", value=False)

    st.subheader("Produits pré-définis")
    # Apply filters
    filtered = [p for p in products if (dep == "Tous" or p.get("department", "") == dep) and (q.lower() in p["name"].lower())]

    # Optional: show only selected products
    if show_selected_only:
        only_selected = []
        for p in filtered:
            sel_key = f"sel_{p['id']}"
            if st.session_state.get(sel_key, False):
                only_selected.append(p)
        filtered = only_selected

    # Grid (3 per row)
    for i, p in enumerate(filtered):
        cols = st.columns(3) if (i % 3) == 0 else cols
        with cols[i % 3]:
            with st.container(border=True):
                # Image
                try:
                    st.image((BASE_DIR / p["image"]).as_posix(), use_column_width=True)
                except Exception:
                    st.write("🖼️ (image introuvable)")

                # Info
                upc = int(p.get("units_per_case", 0) or 0)
                info_line = f"{p.get('department', '')} • ${p.get('unit_price', 0):.2f} / Quantité, une caisse = {upc} Quantités"
                st.markdown(f"**{p['name']}**  \n<span style='color:#6b7280'>{info_line}</span>", unsafe_allow_html=True)

                # Controls
                sel_key = f"sel_{p['id']}"
                qtyu_key = f"qtyu_{p['id']}"
                qtyc_key = f"qtyc_{p['id']}"
                rem_key = f"rem_{p['id']}"

                col_chk, col_u, col_c = st.columns([1, 1, 1])
                with col_chk:
                    selected = st.checkbox("Choisir", key=sel_key)
                prev_units = st.session_state.get(qtyu_key, 0)
                prev_cases = st.session_state.get(qtyc_key, 0)
                if selected and prev_units == 0 and prev_cases == 0:
                    prev_units = 1
                with col_u:
                    st.number_input("Quantité (unités)", min_value=0, step=1, value=prev_units, key=qtyu_key)
                with col_c:
                    st.number_input("Quantité (caisses)", min_value=0, step=1, value=prev_cases, key=qtyc_key)

                st.text_area("Remarque", key=rem_key, height=60, placeholder="Option : découpe/emballage/goût, etc.")

    # -------- Custom products (grid 3 per row) --------
    st.subheader("Produits personnalisés (image OU note + quantité)")
    MAX_CUSTOM = 12
    if "custom_count" not in st.session_state:
        st.session_state.custom_count = 1
    if "custom_data" not in st.session_state:
        st.session_state.custom_data = {}

    def _ensure_row(i: int):
        if i not in st.session_state.custom_data:
            st.session_state.custom_data[i] = {
                "name": "", "remark": "", "qty_units": 0, "qty_cases": 0, "img_bytes": None, "img_name": ""
            }

    def _on_change_text(i: int, field: str, key: str):
        st.session_state.custom_data[i][field] = st.session_state.get(key, "")

    def _on_change_number(i: int, field: str, key: str):
        st.session_state.custom_data[i][field] = int(st.session_state.get(key, 0) or 0)

    def _on_upload(i: int, key: str):
        up = st.session_state.get(key)
        if up is not None:
            st.session_state.custom_data[i]["img_bytes"] = up.getvalue()
            st.session_state.custom_data[i]["img_name"] = up.name

    def _reindex_custom():
        items = [st.session_state.custom_data[k] for k in sorted(st.session_state.custom_data.keys()) if k < st.session_state.custom_count]
        st.session_state.custom_data = {i: items[i] for i in range(len(items))}
        st.session_state.custom_count = len(items) if len(items) > 0 else 1
        for i in range(st.session_state.custom_count):
            _ensure_row(i)

    def _add_tile_clicked():
        st.session_state.custom_count = min(st.session_state.custom_count + 1, MAX_CUSTOM)
        _ensure_row(st.session_state.custom_count - 1)

    def _remove_idx(i: int):
        if i in st.session_state.custom_data:
            del st.session_state.custom_data[i]
        _reindex_custom()

    _ensure_row(0)
    count = int(st.session_state.custom_count)
    slots = list(range(min(count + 1, MAX_CUSTOM)))
    per_row = 3
    for row_start in range(0, len(slots), per_row):
        cols = st.columns(per_row, vertical_alignment="top")
        for j, col in enumerate(cols):
            idx = row_start + j
            if idx >= len(slots):
                break
            with col:
                if idx < count:
                    _ensure_row(idx)
                    row = st.session_state.custom_data[idx]
                    with st.container(border=True):
                        h1, h2 = st.columns([3, 1])
                        with h1:
                            st.markdown(f"**Personnalisé #{idx+1}**")
                        with h2:
                            if st.button("Retirer", key=f"rm_{idx}"):
                                _remove_idx(idx)
                                st.rerun()
                        k_name = f"c_name_{idx}"
                        k_img = f"c_img_{idx}"
                        k_rem = f"c_remark_{idx}"
                        k_qtu = f"c_qtyu_{idx}"
                        k_qtc = f"c_qtyc_{idx}"
                        st.text_input(f"Nom (facultatif) #{idx+1}", value=row.get('name', ''), key=k_name,
                                      on_change=_on_change_text, args=(idx, 'name', k_name))
                        st.file_uploader(f"Image (facultatif) #{idx+1}", type=["png", "jpg", "jpeg"],
                                         key=k_img, on_change=_on_upload, args=(idx, k_img))
                        if row.get("img_name"):
                            st.caption(f"📎 Image mise en cache：{row['img_name']} (sera incluse lors de l'envoi)")
                        st.text_area(f"Note (facultatif) #{idx+1}", value=row.get('remark', ''), key=k_rem, height=90,
                                     on_change=_on_change_text, args=(idx, 'remark', k_rem))
                        cu, cc = st.columns([1, 1])
                        with cu:
                            st.number_input(f"Quantité (unités) * #{idx+1}", min_value=0, step=1,
                                            value=int(row.get('qty_units', 0)), key=k_qtu,
                                            on_change=_on_change_number, args=(idx, 'qty_units', k_qtu))
                        with cc:
                            st.number_input(f"Quantité (caisses) * #{idx+1}", min_value=0, step=1,
                                            value=int(row.get('qty_cases', 0)), key=k_qtc,
                                            on_change=_on_change_number, args=(idx, 'qty_cases', k_qtc))
                elif idx == count and count < MAX_CUSTOM:
                    with st.container(border=True):
                        if st.button("➕ Ajouter", key=f"add_{idx}", use_container_width=True):
                            _add_tile_clicked()
                            st.rerun()
                else:
                    st.empty()

    st.divider()
    submit = st.button("✅ Envoyer la commande", type="primary")
    if submit:
        errors = []
        if not (name or "").strip():
            errors.append("Veuillez saisir le nom.")
        if not (phone or "").strip():
            errors.append("Veuillez saisir le téléphone.")
        email = (email or '').strip()
        if not email or not EMAIL_RE.fullmatch(email):
            errors.append("Veuillez saisir une adresse e-mail valide.")

        chosen_items = []
        # Preset products
        for p in products:
            sel = st.session_state.get(f"sel_{p['id']}")
            qty_u = int(st.session_state.get(f"qtyu_{p['id']}", 0))
            qty_c = int(st.session_state.get(f"qtyc_{p['id']}", 0))
            remark = st.session_state.get(f"rem_{p['id']}", "")
            if sel:
                if qty_u <= 0 and qty_c <= 0:
                    errors.append(f"【{p['name']}】：au moins l'une des quantités (unités / caisses) doit être > 0.")
                else:
                    chosen_items.append({
                        "type": "preset",
                        "id": p["id"],
                        "name": p["name"],
                        "qty_units": qty_u,
                        "qty_cases": qty_c,
                        "units_per_case": int(p.get("units_per_case", 0) or 0),
                        "remark": remark,
                        "image_path": p["image"]
                    })

        # Custom entries
        custom_entries = [st.session_state.custom_data[i] for i in sorted(st.session_state.custom_data.keys()) if i < st.session_state.custom_count]
        for ce in custom_entries:
            q_u = int(ce.get("qty_units", 0) or 0)
            q_c = int(ce.get("qty_cases", 0) or 0)
            has_img = bool(ce.get("img_bytes"))
            has_note = bool(str(ce.get("remark", "")).strip())
            if q_u > 0 or q_c > 0:
                if not (has_img or has_note):
                    errors.append("Produit personnalisé : fournir au moins Image ou Note + Quantité.")
                else:
                    chosen_items.append({
                        "type": "custom",
                        "id": None,
                        "name": ce.get("name") or "Produit personnalisé",
                        "qty_units": q_u,
                        "qty_cases": q_c,
                        "units_per_case": 0,
                        "remark": ce.get("remark") or "",
                        "img_bytes": ce.get("img_bytes"),
                        "img_name": ce.get("img_name")
                    })

        if not chosen_items:
            errors.append("Veuillez sélectionner au moins un produit ou un produit personnalisé valide.")

        if errors:
            st.error("Échec :\n- " + "\n- ".join(errors))
        else:
            order_id = gen_order_id(name)
            order_folder = ensure_dir(ORDERS_DIR / order_id)
            # save custom images
            for idx, it in enumerate(chosen_items):
                if it.get("img_bytes"):
                    ext = Path(it.get("img_name") or "").suffix.lower() or ".png"
                    uniq = datetime.now().strftime("%Y%m%d%H%M%S_%f") + "_" + uuid.uuid4().hex[:6]
                    save_path = order_folder / f"custom_{idx+1}_{uniq}{ext}"
                    with open(save_path, "wb") as f:
                        f.write(it["img_bytes"])
                    it["image_path"] = str(save_path.relative_to(BASE_DIR)).replace("\\", "/")
                    it.pop("img_bytes", None)
                    it.pop("img_name", None)

            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            order_data = {
                "order_id": order_id,
                "customer_name": name,
                "phone": phone,
                "email": email,
                "created_at": created_at,
                "status": "Nouveau",
                "items": [{
                    "name": it["name"],
                    "qty_units": int(it.get("qty_units", 0) or 0),
                    "qty_cases": int(it.get("qty_cases", 0) or 0),
                    "units_per_case": int(it.get("units_per_case", 0) or 0),
                    "remark": it.get("remark", ""),
                    "image_path": it.get("image_path")
                } for it in chosen_items]
            }

            pdf_path = order_folder / f"Commande_{order_id}.pdf"
            build_order_pdf(order_data, str(pdf_path))
            (order_folder / "order.json").write_text(json.dumps(order_data, ensure_ascii=False, indent=2), encoding="utf-8")

            subject = f"Xinya_Commandes_{order_id}"
            body = f"Bonjour {name},\n\nVotre commande est créée (ID: {order_id}). Le PDF est en pièce jointe.\n— Xinya Supermarché"
            recipients = [ADMIN_EMAIL, email]
            try:
                send_email_with_attachment(subject, body, recipients, [str(pdf_path)])
                st.success("✅ Commande envoyée ! Le PDF a été expédié à l'admin et au client.")
            except Exception as e:
                st.warning(f"⚠️ L'e-mail n'a pas été envoyé : {e}\nLe PDF a été généré localement.")

            with open(pdf_path, "rb") as f:
                st.download_button("📄 Télécharger le PDF", data=f.read(), file_name=pdf_path.name, mime="application/pdf")
            st.info(f"ID de commande : **{order_id}**")


# ===================== Admin (Back office) =====================
elif tab == "Admin":
    st.title("Administration")

    pwd = st.text_input("Mot de passe admin", type="password")
    if pwd != ADMIN_PASS:
        st.error("Accès refusé. Saisissez le mot de passe admin (.env: ADMIN_PASS).")
        st.stop()

    tab_prod, tab_orders = st.tabs(["🧺 Produits", "📦 Commandes"])

    # ---------- Produits ----------
    with tab_prod:
        products = load_products()
        st.subheader("Ajouter un produit")
        with st.form("add_prod"):
            name = st.text_input("Nom du produit *")
            department = st.text_input("Département *", placeholder="Ex. Fruits / Légumes / Poisson / Épicerie / Crèmerie / Surgelés")
            unit_price = st.number_input("Prix unitaire ($) *", min_value=0.0, step=0.01, format="%.2f")
            upc = st.number_input("Unités par caisse *", min_value=1, step=1, value=12)
            img = st.file_uploader("Image (png/jpg)", type=["png", "jpg", "jpeg"])
            ok = st.form_submit_button("Ajouter")
            if ok:
                errs = []
                if not name: errs.append("Nom requis.")
                if not department: errs.append("Département requis.")
                if unit_price <= 0: errs.append("Prix invalide.")
                if upc <= 0: errs.append("Unités/caisse invalide.")
                if not img: errs.append("Image requise.")
                if errs:
                    st.error("Erreur :\n- " + "\n- ".join(errs))
                else:
                    ensure_dir(PRODUCTS_DIR)
                    ext = Path(img.name).suffix.lower() or ".png"
                    safe = re.sub(r'[^a-zA-Z0-9_-]+', '_', name)[:40]
                    img_path = PRODUCTS_DIR / f"{safe}_{ts_now()}{ext}"
                    with open(img_path, "wb") as out:
                        out.write(img.getbuffer())
                    new_id = _make_unique_pid(set(p["id"] for p in products))
                    products.append({
                        "id": new_id,
                        "name": name,
                        "department": department,
                        "unit_price": float(unit_price),
                        "units_per_case": int(upc),
                        "image": str(img_path.relative_to(BASE_DIR)).replace('\\', '/')
                    })
                    save_products(products)
                    st.success(f"Ajouté : {name}")
                    st.rerun()

        st.subheader("Modifier un produit")
        if products:
            pid = st.selectbox("Choisir l'ID du produit", [p["id"] for p in products])
            p = next(p for p in products if p["id"] == pid)
            with st.form("edit_prod"):
                name_e = st.text_input("Nom", value=p["name"])
                department_e = st.text_input("Département", value=p.get("department", ""))
                price_e = st.number_input("Prix unitaire ($)", min_value=0.0, step=0.01, format="%.2f", value=float(p.get("unit_price", 0)))
                upc_e = st.number_input("Unités par caisse", min_value=1, step=1, value=int(p.get("units_per_case", 12)))
                img_new = st.file_uploader("Remplacer l'image (optionnel)", type=["png", "jpg", "jpeg"])
                ok_e = st.form_submit_button("Enregistrer les modifications")
                if ok_e:
                    old_img_rel = p["image"]
                    if img_new is not None:
                        ensure_dir(PRODUCTS_DIR)
                        ext = Path(img_new.name).suffix.lower() or ".png"
                        safe = re.sub(r'[^a-zA-Z0-9_-]+', '_', name_e)[:40]
                        img_path = PRODUCTS_DIR / f"{safe}_{ts_now()}{ext}"
                        with open(img_path, "wb") as out:
                            out.write(img_new.getbuffer())
                        try:
                            old_path = BASE_DIR / old_img_rel
                            if old_path.exists():
                                old_path.unlink()
                        except Exception:
                            pass
                        p["image"] = str(img_path.relative_to(BASE_DIR)).replace('\\', '/')
                    p["name"] = name_e
                    p["department"] = department_e
                    p["unit_price"] = float(price_e)
                    p["units_per_case"] = int(upc_e)
                    save_products(products)
                    st.success("Produit mis à jour.")
                    st.rerun()
        else:
            st.info("Aucun produit.")

        st.subheader("Importer en lot (CSV / Excel + ZIP d’images)")
        st.caption("字段：name, department, unit_price, units_per_case, image（图片文件名）。支持列名容错：name/nom/Nom；department/dept/category；unit_price/price；units_per_case/per_case/units_per_caisse；image/img。")
        up_data = st.file_uploader("CSV ou Excel", type=["csv", "xlsx"])
        up_zip = st.file_uploader("ZIP d’images (optionnel)", type=["zip"])
        if st.button("Importer"):
            if up_data is None:
                st.error("Veuillez choisir un fichier CSV ou Excel.")
            else:
                try:
                    if up_data.name.lower().endswith(".csv"):
                        df = pd.read_csv(up_data)
                    else:
                        try:
                            df = pd.read_excel(up_data)
                        except Exception as e:
                            if "openpyxl" in str(e):
                                st.error("Lecture échouée：缺少 openpyxl。\n请在虚拟环境中执行：`pip install openpyxl==3.1.2`，或将它加入 requirements.txt 后重新启动。")
                                st.stop()
                            else:
                                raise
                except Exception as e:
                    st.error(f"Lecture échouée：{e}")
                    st.stop()

                def pick(row, keys, default=""):
                    for k in keys:
                        if k in row and not pd.isna(row[k]):
                            return row[k]
                    return default

                zip_map = {}
                if up_zip is not None:
                    try:
                        with zipfile.ZipFile(up_zip) as zf:
                            for n in zf.namelist():
                                zip_map[Path(n).name] = zf.read(n)
                    except Exception as e:
                        st.error(f"ZIP 无法读取：{e}")
                        st.stop()

                products = load_products()
                added = 0
                ensure_dir(PRODUCTS_DIR)
                existing_ids = set(p["id"] for p in products)
                for _, r in df.iterrows():
                    name = str(pick(r, ["name", "nom", "Nom"], "")).strip()
                    dep = str(pick(r, ["department", "dept", "category"], "")).strip()
                    # parse price & upc
                    price_raw = pick(r, ["unit_price", "price"], 0)
                    try:
                        price = float(str(price_raw).replace(",", ".").strip())
                    except Exception:
                        price = 0.0
                    upc_raw = pick(r, ["units_per_case", "per_case", "units_per_caisse"], 0)
                    try:
                        upc = int(float(str(upc_raw).strip()))
                    except Exception:
                        upc = 0
                    img_name = str(pick(r, ["image", "img"], "")).strip()

                    if not (name and dep and price > 0 and upc > 0 and img_name):
                        continue

                    img_bytes = zip_map.get(Path(img_name).name) if up_zip is not None else None
                    if img_bytes is None:
                        # 没有提供 ZIP 或找不到对应图片 -> 跳过
                        continue

                    safe = re.sub(r'[^a-zA-Z0-9_-]+', '_', name)[:40]
                    ext = Path(img_name).suffix.lower() or ".png"
                    img_path = PRODUCTS_DIR / f"{safe}_{ts_now()}{ext}"
                    with open(img_path, "wb") as f:
                        f.write(img_bytes)

                    new_id = _make_unique_pid(existing_ids)
                    existing_ids.add(new_id)
                    products.append({
                        "id": new_id,
                        "name": name,
                        "department": dep,
                        "unit_price": float(price),
                        "units_per_case": int(upc),
                        "image": str(img_path.relative_to(BASE_DIR)).replace('\\', '/')
                    })
                    added += 1

                save_products(products)
                st.success(f"导入完成：{added} 条。")
                st.rerun()

        st.subheader("Liste des produits")
        dfp = pd.DataFrame(load_products())
        if not dfp.empty:
            st.dataframe(dfp[["id", "name", "department", "unit_price", "units_per_case", "image"]], use_container_width=True, hide_index=True)
        else:
            st.info("Aucun produit.")

        st.subheader("Supprimer un produit")
        id_to_del = st.selectbox("Choisir l'ID à supprimer", [""] + [p["id"] for p in load_products()])
        if st.button("Supprimer"):
            if not id_to_del:
                st.warning("Sélectionnez un ID.")
            else:
                products = load_products()
                remain = []
                removed = None
                for p in products:
                    if p["id"] == id_to_del:
                        removed = p
                    else:
                        remain.append(p)
                if removed:
                    try:
                        old = BASE_DIR / removed["image"]
                        if old.exists():
                            old.unlink()
                    except Exception:
                        pass
                    save_products(remain)
                    st.success(f"Supprimé : {removed['name']}")
                    st.rerun()

    # ---------- Commandes ----------
    with tab_orders:
        st.subheader("Tableau de bord des commandes")
        colf1, colf2, colf3 = st.columns([1, 1, 2])
        with colf1:
            d1 = st.date_input("Du", value=date.today().replace(day=1))
        with colf2:
            d2 = st.date_input("Au", value=date.today())
        with colf3:
            kw = st.text_input("Client contient", value="")
        stt = st.selectbox("Statut", ["(tous)", "Nouveau", "Traitement", "Envoyé", "Annulé"], index=0)

        rows = []
        if ORDERS_DIR.exists():
            for d in ORDERS_DIR.iterdir():
                if d.is_dir() and (d / "order.json").exists():
                    rec = json.loads((d / "order.json").read_text(encoding="utf-8"))
                    rec["folder"] = str(d)
                    # filters
                    try:
                        dt = datetime.fromisoformat(rec.get("created_at", "")).date()
                    except Exception:
                        dt = date.today()
                    if not (d1 <= dt <= d2):
                        continue
                    if kw and kw.lower() not in rec.get("customer_name", "").lower():
                        continue
                    if stt != "(tous)" and rec.get("status") != stt:
                        continue
                    n_items = len(rec.get("items", []))
                    total_units = sum(int(it.get("qty_units", 0) or 0) + int(it.get("qty_cases", 0) or 0) * int(it.get("units_per_case", 0) or 0) for it in rec.get("items", []))
                    rows.append({
                        "Date": rec.get("created_at", ""),
                        "ID": rec.get("order_id", ""),
                        "Client": rec.get("customer_name", ""),
                        "Téléphone": rec.get("phone", ""),
                        "E-mail": rec.get("email", ""),
                        "Articles": n_items,
                        "Total (unités)": total_units,
                        "Statut": rec.get("status", "Nouveau")
                    })
        dfo = pd.DataFrame(rows)
        st.dataframe(dfo, use_container_width=True, hide_index=True)
        if not dfo.empty:
            st.download_button("⬇️ Exporter CSV", data=dfo.to_csv(index=False).encode("utf-8-sig"), file_name="commandes_export.csv", mime="text/csv")

        st.subheader("Détail / mise à jour")
        order_ids = [r["ID"] for r in rows]
        selected_id = st.selectbox("Choisir l'ID de commande", [""] + order_ids)
        if selected_id:
            # find rec
            rec = None
            folder = None
            for d in ORDERS_DIR.iterdir():
                jf = d / "order.json"
                if jf.exists():
                    temp = json.loads(jf.read_text(encoding="utf-8"))
                    if temp.get("order_id") == selected_id:
                        rec = temp
                        folder = str(d)
                        break
            if rec:
                st.write(f"**Client** : {rec.get('customer_name')}  |  **Créé le** : {rec.get('created_at')}  |  **Statut** : {rec.get('status')}")
                items_data = []
                for it in rec.get("items", []):
                    q_u = int(it.get("qty_units", 0) or 0)
                    q_c = int(it.get("qty_cases", 0) or 0)
                    upc = int(it.get("units_per_case", 0) or 0)
                    parts = []
                    if q_u > 0: parts.append(f"{q_u} unités")
                    if q_c > 0: parts.append(f"{q_c} caisses")
                    if upc and q_c > 0: parts.append(f"Total {q_u + q_c * upc} unités")
                    items_data.append({"Produit": it["name"], "Qté": " | ".join(parts), "Remarque": it.get("remark", "")})
                st.table(pd.DataFrame(items_data))
                new_status = st.selectbox("Changer le statut", ["Nouveau", "Traitement", "Envoyé", "Annulé"],
                                          index=["Nouveau", "Traitement", "Envoyé", "Annulé"].index(rec.get("status", "Nouveau")))
                if st.button("Enregistrer le statut"):
                    rec["status"] = new_status
                    (Path(folder) / "order.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
                    st.success("Statut mis à jour.")
                pdf_path = Path(folder) / f"Commande_{rec.get('order_id')}.pdf"
                if pdf_path.exists():
                    with open(pdf_path, "rb") as f:
                        st.download_button("📄 Télécharger le PDF de cette commande", data=f.read(), file_name=pdf_path.name, mime="application/pdf")
                else:
                    st.info("PDF introuvable.")
