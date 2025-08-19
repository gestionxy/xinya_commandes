
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
PRODUCTS_DIR = ASSETS_DIR / "products"
ORDERS_DIR = BASE_DIR / "orders"

PRODUCTS_JSON = DATA_DIR / "products.json"

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)
    return p
