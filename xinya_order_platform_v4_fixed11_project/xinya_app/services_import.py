
import zipfile
from pathlib import Path
import pandas as pd
import streamlit as st
from .paths import PRODUCTS_DIR, BASE_DIR
from .ids import make_unique_pid
from .repo_products import load_products, save_products
from utils.image_utils import normalize_image_bytes
import re

def _pick(row, keys, default=""):
    for k in keys:
        if k in row and not pd.isna(row[k]):
            return row[k]
    return default

def import_products_from_table(df: pd.DataFrame, zip_bytes: bytes|None) -> int:
    zip_map = {}
    if zip_bytes:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:  # noqa: F821
            for n in zf.namelist():
                zip_map[Path(n).name] = zf.read(n)

    products = load_products()
    existing_ids = set(p["id"] for p in products)
    added = 0
    for _, r in df.iterrows():
        name = str(_pick(r, ["name","nom","Nom"], "")).strip()
        dep  = str(_pick(r, ["department","dept","category"], "")).strip()
        price_raw = _pick(r,["unit_price","price"],0)
        try: price = float(str(price_raw).replace(",",".").strip())
        except: price = 0.0
        upc_raw = _pick(r,["units_per_case","per_case","units_per_caisse"],0)
        try: upc = int(float(str(upc_raw).strip()))
        except: upc = 0
        img_name = str(_pick(r,["image","img"],""))
        if not (name and dep and price>0 and upc>0 and img_name):
            continue
        img_bytes = zip_map.get(Path(img_name).name) if zip_map else None
        if img_bytes is None: 
            continue
        safe = re.sub(r'[^a-zA-Z0-9_-]+','_',name)[:40]
        out = (PRODUCTS_DIR / f"{safe}_import.jpg")
        out.parent.mkdir(parents=True, exist_ok=True)
        norm = normalize_image_bytes(img_bytes, 800, 600)
        out.write_bytes(norm)
        new_id = make_unique_pid(existing_ids); existing_ids.add(new_id)
        products.append({
            "id": new_id, "name": name, "department": dep,
            "unit_price": float(price), "units_per_case": int(upc),
            "image": str(out.relative_to(BASE_DIR)).replace('\\','/')
        })
        added += 1
    save_products(products)
    return added
