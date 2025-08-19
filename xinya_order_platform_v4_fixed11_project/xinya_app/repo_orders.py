
import json
from .paths import ORDERS_DIR
from pathlib import Path

def save_order(folder: Path, data: dict):
    (folder / "order.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
