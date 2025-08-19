
from pathlib import Path
from datetime import datetime, date
import io, zipfile, re
import pandas as pd
import streamlit as st
from .config import ADMIN_PASS
from .paths import BASE_DIR, PRODUCTS_DIR, ORDERS_DIR, ensure_dir
from .repo_products import load_products, save_products
from .ids import ts_now, make_unique_pid
from utils.image_utils import normalize_image_bytes
from utils.pdf_utils import build_order_pdf

def render_admin_page():
    pwd = st.text_input("Mot de passe admin", type="password")
    if pwd != ADMIN_PASS:
        st.error("Accès refusé. Saisissez le mot de passe admin (.env: ADMIN_PASS)." )
        st.stop()

    tab_prod, tab_orders = st.tabs(["🧺 Produits", "📦 Commandes"])

    with tab_prod:
        products = load_products()
        st.subheader("Ajouter un produit")
        with st.form("add_prod"):
            name = st.text_input("Nom du produit *")
            department = st.text_input("Département *")
            unit_price = st.number_input("Prix unitaire ($) *", min_value=0.0, step=0.01, format="%.2f")
            upc = st.number_input("Unités par caisse *", min_value=1, step=1, value=12)
            img = st.file_uploader("Image (png/jpg)", type=["png","jpg","jpeg"])
            ok = st.form_submit_button("Ajouter")
            if ok:
                errs=[]; 
                if not name: errs.append("Nom requis.")
                if not department: errs.append("Département requis.")
                if unit_price<=0: errs.append("Prix invalide.")
                if upc<=0: errs.append("Unités/caisse invalide.")
                if not img: errs.append("Image requise.")
                if errs:
                    st.error("Erreur :\n- "+"\n- ".join(errs))
                else:
                    ensure_dir(PRODUCTS_DIR)
                    ext = Path(img.name).suffix.lower() or ".jpg"
                    safe = re.sub(r'[^a-zA-Z0-9_-]+','_',name)[:40]
                    out = PRODUCTS_DIR / f"{safe}_{ts_now()}{ext}"
                    norm = normalize_image_bytes(img.getbuffer(), 800, 600)
                    with open(out.with_suffix('.jpg'), 'wb') as f: f.write(norm)
                    out = out.with_suffix('.jpg')
                    new_id = make_unique_pid(set(p["id"] for p in products))
                    products.append({"id":new_id,"name":name,"department":department,"unit_price":float(unit_price),"units_per_case":int(upc),"image":str(out.relative_to(BASE_DIR)).replace('\\','/')})
                    save_products(products)
                    st.success(f"Ajouté : {name}"); st.rerun()

        st.subheader("Modifier un produit")
        if products:
            pid = st.selectbox("Choisir l'ID du produit", [p["id"] for p in products])
            p = next(x for x in products if x["id"]==pid)
            with st.form("edit_prod"):
                name_e = st.text_input("Nom", value=p["name"])
                department_e = st.text_input("Département", value=p.get("department",""))
                price_e = st.number_input("Prix unitaire ($)", min_value=0.0, step=0.01, format="%.2f", value=float(p.get("unit_price",0)))
                upc_e = st.number_input("Unités par caisse", min_value=1, step=1, value=int(p.get("units_per_case",12)))
                img_new = st.file_uploader("Remplacer l'image (optionnel)", type=["png","jpg","jpeg"])                
                ok_e = st.form_submit_button("Enregistrer les modifications")
                if ok_e:
                    if img_new is not None:
                        ensure_dir(PRODUCTS_DIR)
                        ext = Path(img_new.name).suffix.lower() or ".jpg"
                        safe = re.sub(r'[^a-zA-Z0-9_-]+','_',name_e)[:40]
                        out = PRODUCTS_DIR / f"{safe}_{ts_now()}{ext}"
                        norm = normalize_image_bytes(img_new.getbuffer(), 800, 600)
                        with open(out.with_suffix('.jpg'),'wb') as f: f.write(norm)
                        out = out.with_suffix('.jpg')
                        try:
                            old = BASE_DIR / p["image"]; 
                            if old.exists(): old.unlink()
                        except Exception: pass
                        p["image"] = str(out.relative_to(BASE_DIR)).replace('\\','/')
                    p["name"]=name_e; p["department"]=department_e; p["unit_price"]=float(price_e); p["units_per_case"]=int(upc_e)
                    save_products(products); st.success("Produit mis à jour."); st.rerun()
        else:
            st.info("Aucun produit.")

        st.subheader("Importer en lot (CSV / Excel + ZIP d’images)")
        st.caption("列：name, department, unit_price, units_per_case, image（图片文件名）。支持列名容错。")
        up_data = st.file_uploader("CSV ou Excel", type=["csv","xlsx"])
        up_zip  = st.file_uploader("ZIP d’images (optionnel)", type=["zip"])            
        if st.button("Importer"):
            if up_data is None: st.error("Veuillez choisir un fichier CSV ou Excel.")
            else:
                try:
                    if up_data.name.lower().endswith('.csv'):
                        df = pd.read_csv(up_data)
                    else:
                        try:
                            df = pd.read_excel(up_data)
                        except Exception as e:
                            if 'openpyxl' in str(e):
                                st.error("Lecture échouée：缺少 openpyxl。请安装：pip install openpyxl==3.1.2"); st.stop()
                            raise
                except Exception as e:
                    st.error(f"Lecture échouée：{e}"); st.stop()
                # Read zip map
                zip_map={}
                if up_zip is not None:
                    try:
                        with zipfile.ZipFile(up_zip) as zf:
                            for n in zf.namelist():
                                zip_map[Path(n).name]=zf.read(n)
                    except Exception as e:
                        st.error(f"ZIP 无法读取：{e}"); st.stop()
                products = load_products(); existing = set(p['id'] for p in products); added=0
                ensure_dir(PRODUCTS_DIR)
                for _, r in df.iterrows():
                    name=str(r.get('name', r.get('nom', r.get('Nom','')))).strip()
                    dep=str(r.get('department', r.get('dept', r.get('category','')))).strip()
                    try: price=float(str(r.get('unit_price', r.get('price',0))).replace(',','.'))
                    except: price=0.0
                    try: upc=int(float(str(r.get('units_per_case', r.get('per_case', r.get('units_per_caisse',0))))))
                    except: upc=0
                    img_name=str(r.get('image', r.get('img',''))).strip()
                    if not (name and dep and price>0 and upc>0 and img_name): 
                        continue
                    img_bytes=zip_map.get(Path(img_name).name) if up_zip is not None else None
                    if img_bytes is None: continue
                    safe = re.sub(r'[^a-zA-Z0-9_-]+','_',name)[:40]
                    out = PRODUCTS_DIR / f"{safe}_{ts_now()}.jpg"
                    norm = normalize_image_bytes(img_bytes, 800, 600); Path(out).write_bytes(norm)
                    new_id = make_unique_pid(existing); existing.add(new_id)
                    products.append({"id":new_id,"name":name,"department":dep,"unit_price":float(price),"units_per_case":int(upc),"image":str(out.relative_to(BASE_DIR)).replace('\\','/')})
                    added+=1
                save_products(products); st.success(f"导入完成：{added} 条。"); st.rerun()

        st.subheader("Liste des produits")
        dfp = pd.DataFrame(load_products())
        if not dfp.empty:
            st.dataframe(dfp[["id","name","department","unit_price","units_per_case","image"]], use_container_width=True, hide_index=True)
        else:
            st.info("Aucun produit.")

        st.subheader("Supprimer un produit")
        id_to_del = st.selectbox("Choisir l'ID à supprimer", [""]+[p["id"] for p in load_products()])
        if st.button("Supprimer"):
            if not id_to_del: st.warning("Sélectionnez un ID.")
            else:
                products=load_products(); remain=[]; removed=None
                for p in products:
                    if p["id"]==id_to_del: removed=p
                    else: remain.append(p)
                if removed:
                    try:
                        old = BASE_DIR / removed["image"]; 
                        if old.exists(): old.unlink()
                    except Exception: pass
                    save_products(remain); st.success(f"Supprimé : {removed['name']}"); st.rerun()

    with tab_orders:
        st.subheader("Tableau de bord des commandes")
        c1,c2,c3=st.columns([1,1,2])
        with c1: d1=st.date_input("Du", value=date.today().replace(day=1))
        with c2: d2=st.date_input("Au", value=date.today())
        with c3: kw=st.text_input("Client contient", "")
        stt=st.selectbox("Statut", ["(tous)","Nouveau","Traitement","Envoyé","Annulé"], index=0)

        rows=[]
        if ORDERS_DIR.exists():
            for d in ORDERS_DIR.iterdir():
                jf=d/"order.json"
                if jf.exists():
                    rec=json.loads(jf.read_text(encoding='utf-8')); rec["folder"]=str(d)
                    try: dt=datetime.fromisoformat(rec.get("created_at","")); 
                    except: continue
                    if not (d1<=dt.date()<=d2): continue
                    if kw and kw.lower() not in rec.get("customer_name","").lower(): continue
                    if stt != "(tous)" and rec.get("status")!=stt: continue
                    n=len(rec.get("items",[]))
                    total=sum(int(it.get('qty_units',0) or 0)+int(it.get('qty_cases',0) or 0)*int(it.get('units_per_case',0) or 0) for it in rec.get('items',[]))
                    rows.append({"Date":rec.get("created_at",""),"ID":rec.get("order_id",""),"Client":rec.get("customer_name",""),"Téléphone":rec.get("phone",""),"E-mail":rec.get("email",""),"Articles":n,"Total (unités)":total,"Statut":rec.get("status","Nouveau")})
        dfo=pd.DataFrame(rows); st.dataframe(dfo, use_container_width=True, hide_index=True)
        if not dfo.empty:
            st.download_button("⬇️ Exporter CSV", data=dfo.to_csv(index=False).encode('utf-8-sig'), file_name="commandes_export.csv", mime="text/csv")
        st.subheader("Détail / mise à jour")
        order_ids=[r["ID"] for r in rows]
        sel=st.selectbox("Choisir l'ID de commande", [""]+order_ids)
        if sel:
            folder=None; rec=None
            for d in ORDERS_DIR.iterdir():
                jf=d/"order.json"
                if jf.exists():
                    tmp=json.loads(jf.read_text(encoding='utf-8'))
                    if tmp.get("order_id")==sel:
                        rec=tmp; folder=str(d); break
            if rec:
                st.write(f"**Client** : {rec.get('customer_name')}  |  **Créé le** : {rec.get('created_at')}  |  **Statut** : {rec.get('status')}")
                items=[]
                for it in rec.get("items",[]):
                    u=int(it.get('qty_units',0) or 0); c=int(it.get('qty_cases',0) or 0); upc=int(it.get('units_per_case',0) or 0)
                    parts=[]; 
                    if u>0: parts.append(f"{u} unités")
                    if c>0: parts.append(f"{c} caisses")
                    if upc and c>0: parts.append(f"Total {u+c*upc} unités")
                    items.append({"Produit":it.get('name',''),"Qté":" | ".join(parts),"Remarque":it.get('remark','')})
                st.table(pd.DataFrame(items))
                new_status=st.selectbox("Changer le statut", ["Nouveau","Traitement","Envoyé","Annulé"], index=["Nouveau","Traitement","Envoyé","Annulé"].index(rec.get("status","Nouveau")))
                if st.button("Enregistrer le statut"):
                    rec["status"]=new_status; (Path(folder)/"order.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding='utf-8'); st.success("Statut mis à jour.")
                pdfp=Path(folder)/f"Commande_{rec.get('order_id')}.pdf"
                if pdfp.exists():
                    with open(pdfp,"rb") as f: st.download_button("📄 Télécharger le PDF de cette commande", data=f.read(), file_name=pdfp.name, mime="application/pdf")
                else: st.info("PDF introuvable.")
