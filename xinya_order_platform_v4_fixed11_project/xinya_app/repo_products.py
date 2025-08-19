
import json, re
from pathlib import Path
import streamlit as st
from .paths import PRODUCTS_JSON
@st.cache_data
def load_products():
    if not PRODUCTS_JSON.exists():
        return []
    data = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
    for p in data:
        if "units_per_case" not in p:
            p["units_per_case"] = 12
    return data

def save_products(data):
    PRODUCTS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    load_products.clear()
