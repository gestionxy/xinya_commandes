
import uuid, re
from pathlib import Path
from datetime import datetime
import streamlit as st
import pandas as pd
from .config import ADMIN_EMAIL, EMAIL_RE, email_config_ok
from .paths import BASE_DIR, ORDERS_DIR, ensure_dir
from .repo_products import load_products
from .ids import gen_order_id
from .services_pdf import build_order_pdf
from .services_email import send_email_with_attachment
from utils.image_utils import normalize_image_bytes
from utils.storage_github import GitHubStorage
def render_client_page():
    st.title("🛒 Xinya Supermarché | Plateforme de commande")
    with st.sidebar:
        st.header("Client")
        name = st.text_input("Nom *", max_chars=40)
        phone = st.text_input("Téléphone *", max_chars=30)
        email = st.text_input("E-mail *", max_chars=80)
        st.markdown(f"**Courriel admin** : `{ADMIN_EMAIL}`")
    products = load_products()
    departments = sorted(set(p.get("department", "") for p in products))
    col_search, col_dep, col_sel_only = st.columns([2,1,1])
    with col_search:
        q = st.text_input("🔎 Rechercher un produit", "")
    with col_dep:
        dep = st.selectbox("Département", ["Tous"]+departments, index=0)
    with col_sel_only:
        show_selected_only = st.toggle("Afficher sélectionnés uniquement", False)
    st.subheader("Produits pré-définis")
    filtered = [p for p in products if (dep=="Tous" or p.get("department","")==dep) and (q.lower() in p["name"].lower())]
    if show_selected_only:
        filtered = [p for p in filtered if st.session_state.get(f"sel_{p['id']}", False)]
    for i, p in enumerate(filtered):
        cols = st.columns(3) if (i%3)==0 else cols
        with cols[i%3]:
            with st.container(border=True):
                try:
                    st.image((BASE_DIR / p["image"]).as_posix(), use_column_width=True)
                except Exception:
                    st.write("🖼️ (image introuvable)")
                upc = int(p.get("units_per_case",0) or 0)
                info = f"{p.get('department','')} • ${p.get('unit_price',0):.2f} / Quantité, une caisse = {upc} Quantités"
                st.markdown(f"**{p['name']}**  \n<span style='color:#6b7280'>{info}</span>", unsafe_allow_html=True)
                sel_key=f"sel_{p['id']}"; qtyu_key=f"qtyu_{p['id']}"; qtyc_key=f"qtyc_{p['id']}"; rem_key=f"rem_{p['id']}"
                c1,c2,c3=st.columns([1,1,1])
                with c1: selected = st.checkbox("Choisir", key=sel_key)
                prev_u=st.session_state.get(qtyu_key,0); prev_c=st.session_state.get(qtyc_key,0)
                if selected and prev_u==0 and prev_c==0: prev_u=1
                with c2: st.number_input("Quantité (unités)", min_value=0, step=1, value=prev_u, key=qtyu_key)
                with c3: st.number_input("Quantité (caisses)", min_value=0, step=1, value=prev_c, key=qtyc_key)
                st.text_area("Remarque", key=rem_key, height=60, placeholder="Option : découpe/emballage/goût, etc.")
    st.subheader("Produits personnalisés (image OU note + quantité)")
    MAX_CUSTOM=12
    if "custom_count" not in st.session_state: st.session_state.custom_count=1
    if "custom_data" not in st.session_state: st.session_state.custom_data={}
    def _ensure_row(i:int):
        if i not in st.session_state.custom_data:
            st.session_state.custom_data[i]={"name":"","remark":"","qty_units":0,"qty_cases":0,"img_bytes":None,"img_name":""}
    def _on_text(i, field, key): st.session_state.custom_data[i][field]=st.session_state.get(key,"")
    def _on_num(i, field, key):  st.session_state.custom_data[i][field]=int(st.session_state.get(key,0) or 0)
    def _on_upload(i, key):
        up=st.session_state.get(key)
        if up is not None:
            st.session_state.custom_data[i]["img_bytes"]=up.getvalue()
            st.session_state.custom_data[i]["img_name"]=up.name
    def _reindex():
        items=[st.session_state.custom_data[k] for k in sorted(st.session_state.custom_data.keys()) if k<st.session_state.custom_count]
        st.session_state.custom_data={i:items[i] for i in range(len(items))}
        st.session_state.custom_count = len(items) if len(items)>0 else 1
        for i in range(st.session_state.custom_count): _ensure_row(i)
    def _add(): st.session_state.custom_count=min(st.session_state.custom_count+1, MAX_CUSTOM); _ensure_row(st.session_state.custom_count-1)
    def _rm(i): st.session_state.custom_data.pop(i, None); _reindex()
    _ensure_row(0); count=int(st.session_state.custom_count); slots=list(range(min(count+1, MAX_CUSTOM))); per_row=3
    for row_start in range(0, len(slots), per_row):
        cols=st.columns(per_row, vertical_alignment="top")
        for j, col in enumerate(cols):
            idx=row_start+j
            if idx>=len(slots): break
            with col:
                if idx<count:
                    _ensure_row(idx); row=st.session_state.custom_data[idx]
                    with st.container(border=True):
                        h1,h2=st.columns([3,1])
                        with h1: st.markdown(f"**Personnalisé #{idx+1}**")
                        with h2:
                            if st.button("Retirer", key=f"rm_{idx}"): _rm(idx); st.rerun()
                        kN=f"c_name_{idx}"; kI=f"c_img_{idx}"; kR=f"c_rem_{idx}"; kU=f"c_u_{idx}"; kC=f"c_c_{idx}"
                        st.text_input(f"Nom (facultatif) #{idx+1}", value=row.get('name',''), key=kN, on_change=_on_text, args=(idx,'name',kN))
                        st.file_uploader(f"Image (facultatif) #{idx+1}", type=["png","jpg","jpeg"], key=kI, on_change=_on_upload, args=(idx,kI))
                        if row.get("img_name"): st.caption(f"📎 Image mise en cache：{row['img_name']}")
                        st.text_area(f"Note (facultatif) #{idx+1}", value=row.get('remark',''), key=kR, height=90, on_change=_on_text, args=(idx,'remark',kR))
                        cU,cC=st.columns([1,1])
                        with cU: st.number_input(f"Quantité (unités) * #{idx+1}", min_value=0, step=1, value=int(row.get('qty_units',0)), key=kU, on_change=_on_num, args=(idx,'qty_units',kU))
                        with cC: st.number_input(f"Quantité (caisses) * #{idx+1}", min_value=0, step=1, value=int(row.get('qty_cases',0)), key=kC, on_change=_on_num, args=(idx,'qty_cases',kC))
                elif idx==count and count<MAX_CUSTOM:
                    with st.container(border=True):
                        if st.button("➕ Ajouter", key=f"add_{idx}", use_container_width=True): _add(); st.rerun()
                else:
                    st.empty()
    st.divider()
    submit = st.button("✅ Envoyer la commande", type="primary")
    if submit:
        errors=[]
        if not (name or "").strip(): errors.append("Veuillez saisir le nom.")
        if not (phone or "").strip(): errors.append("Veuillez saisir le téléphone.")
        em=(email or '').strip()
        if not em or not EMAIL_RE.fullmatch(em): errors.append("Veuillez saisir une adresse e-mail valide.")
        chosen=[]
        for p in products:
            sel=st.session_state.get(f"sel_{p['id']}")
            u=int(st.session_state.get(f"qtyu_{p['id']}",0)); c=int(st.session_state.get(f"qtyc_{p['id']}",0))
            r=st.session_state.get(f"rem_{p['id']}", "")
            if sel:
                if u<=0 and c<=0: errors.append(f"【{p['name']}】：au moins l'une des quantités doit être > 0.")
                else:
                    chosen.append({"type":"preset","name":p["name"],"qty_units":u,"qty_cases":c,"units_per_case":int(p.get("units_per_case",0) or 0),"remark":r,"image_path":p["image"]})
        customs=[st.session_state.custom_data[i] for i in sorted(st.session_state.custom_data.keys()) if i<st.session_state.custom_count]
        for ce in customs:
            u=int(ce.get("qty_units",0) or 0); c=int(ce.get("qty_cases",0) or 0)
            has_img=bool(ce.get("img_bytes")); has_note=bool(str(ce.get("remark","")).strip())
            if u>0 or c>0:
                if not (has_img or has_note): errors.append("Produit personnalisé : fournir au moins Image ou Note + Quantité.")
                else:
                    chosen.append({"type":"custom","name":ce.get("name") or "Produit personnalisé","qty_units":u,"qty_cases":c,"units_per_case":0,"remark":ce.get("remark") or "","img_bytes":ce.get("img_bytes"),"img_name":ce.get("img_name")})
        if not chosen: errors.append("Veuillez sélectionner au moins un produit valide.")
        if errors:
            st.error("Échec :\n- " + "\n- ".join(errors)); return
        order_id = gen_order_id(name)
        order_folder = ensure_dir(ORDERS_DIR / order_id)
        for idx,it in enumerate(chosen):
            if it.get("img_bytes"):
                fname = order_folder / f"custom_{idx+1}_{datetime.now().strftime('%Y%m%d%H%M%S_%f')}.jpg"
                Path(fname).write_bytes(normalize_image_bytes(it["img_bytes"], 800, 600))
                it["image_path"] = str(fname.relative_to(BASE_DIR)).replace('\\','/')
                it.pop("img_bytes", None); it.pop("img_name", None)
        order_data = {"order_id":order_id,"customer_name":name,"phone":phone,"email":em,"created_at":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"status":"Nouveau","items":[{"name":x["name"],"qty_units":int(x.get("qty_units",0) or 0),"qty_cases":int(x.get("qty_cases",0) or 0),"units_per_case":int(x.get("units_per_case",0) or 0),"remark":x.get("remark",""),"image_path":x.get("image_path")} for x in chosen]}
        pdf_path = order_folder / f"Commande_{order_id}.pdf"
        from utils import pdf_utils as _pdf
        _pdf.build_order_pdf(order_data, str(pdf_path))
        (order_folder / "order.json").write_text(__import__("json").dumps(order_data, ensure_ascii=False, indent=2), encoding="utf-8")
        subject = f"Xinya_Commandes_{order_id}"
        body = f"Bonjour {name},\n\nVotre commande est créée (ID: {order_id}). Le PDF est en pièce jointe."
        try:
            from utils import email_utils as _email
            _email.send_email_with_attachment(subject, body, [ADMIN_EMAIL, em], [str(pdf_path)])
            st.success("✅ Commande envoyée ! Le PDF a été expédié à l'admin et au client.")
        except Exception as e:
            st.warning(f"⚠️ L'e-mail n'a pas été envoyé : {e}\nLe PDF a été généré localement.")
        try:
            se = st.secrets
            storage = GitHubStorage(
                token=se["GITHUB_TOKEN"],
                repo=se["GITHUB_REPO"],
                branch=se.get("GITHUB_BRANCH", "main"),
                base_path=se.get("GITHUB_BASE_PATH", "orders")
            )
            remote_dir = f"{order_id}"
            with open(pdf_path, "rb") as f:
                storage.upload_bytes(f"{remote_dir}/Commande_{order_id}.pdf", f.read(),
                                    commit_message=f"order {order_id}: add pdf")
            with open(order_folder / "order.json", "rb") as f:
                storage.upload_bytes(f"{remote_dir}/order.json", f.read(),
                                    commit_message=f"order {order_id}: add metadata")
            st.success("☁️ 已将订单备份到 GitHub。")
        except Exception as e:
            st.warning(f"云端持久化失败（GitHub）：{e}")
        with open(pdf_path, "rb") as f:
            st.download_button("📄 Télécharger le PDF", data=f.read(), file_name=pdf_path.name, mime="application/pdf")
        st.info(f"ID de commande : **{order_id}**")
