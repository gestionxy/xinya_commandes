
from datetime import datetime
import re, uuid, json
from .paths import PRODUCTS_JSON
def ts_now():
    return datetime.now().strftime("%Y%m%d%H%M%S")
def gen_order_id(customer_name: str):
    clean = re.sub(r"\s+", "", customer_name or "").strip()
    return f"{clean}_{ts_now()}"
def make_unique_pid(existing: set) -> str:
    while True:
        new_id = "p" + datetime.now().strftime("%Y%m%d%H%M%S_%f") + "_" + uuid.uuid4().hex[:4]
        if new_id not in existing:
            return new_id
def fix_duplicate_product_ids_file():
    try:
        p = PRODUCTS_JSON
        if not p.exists():
            return False, 0
        data = json.loads(p.read_text(encoding="utf-8"))
        seen = set(); changed=False; cnt=0
        for prod in data:
            pid = str(prod.get("id","")).strip()
            if not pid or pid in seen:
                prod["id"] = make_unique_pid(seen); changed=True; cnt+=1
            seen.add(prod["id"])
        if changed:
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return changed, cnt
    except Exception:
        return False, 0
