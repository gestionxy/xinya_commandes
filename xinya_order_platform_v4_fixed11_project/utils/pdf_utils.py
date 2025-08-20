# utils/pdf_utils.py
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

TITLE = "Xinya Supermarché — Bon de commande"

# ---------- Font handling (CJK-safe) ----------
FONT_REG = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

def _try_register_font(name_hint: str, file_candidates):
    for fp in file_candidates:
        p = Path(fp)
        if p.is_file():
            try:
                pdfmetrics.registerFont(TTFont(name_hint, str(p)))
                return name_hint
            except Exception:
                pass
    return None

def _ensure_fonts():
    global FONT_REG, FONT_BOLD
    # candidates for Noto/SourceHan (put your font files in any of these paths)
    reg_candidates = [
        "utils/fonts/NotoSansSC-Regular.otf",
        "utils/fonts/NotoSansSC-Regular.ttf",
        "assets/fonts/NotoSansSC-Regular.otf",
        "assets/fonts/NotoSansSC-Regular.ttf",
        "utils/fonts/SourceHanSansSC-Regular.otf",
        "assets/fonts/SourceHanSansSC-Regular.otf",
    ]
    bold_candidates = [
        "utils/fonts/NotoSansSC-Bold.otf",
        "utils/fonts/NotoSansSC-Bold.ttf",
        "assets/fonts/NotoSansSC-Bold.otf",
        "assets/fonts/NotoSansSC-Bold.ttf",
        "utils/fonts/SourceHanSansSC-Bold.otf",
        "assets/fonts/SourceHanSansSC-Bold.otf",
    ]
    reg = _try_register_font("XN_Regular", reg_candidates)
    bld = _try_register_font("XN_Bold", bold_candidates)
    if reg:
        FONT_REG = reg
    if reg and bld:
        FONT_BOLD = bld
    elif reg and not bld:
        # fallback: use regular font for bold too
        FONT_BOLD = reg

# ---------- Text wrapping with chosen font ----------
def wrap(text, font_name, size, max_w):
    if not text:
        return []
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(test, font_name, size) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def pluralize(n, sing, plur):
    try:
        n = int(n)
    except Exception:
        return f"{n} {plur}"
    return f"{n} {sing if n == 1 else plur}"

def _leading(sz):
    # comfortable line spacing to avoid overlap
    return int(sz * 1.35)

def _draw_header(c, w, h, meta):
    left = 15*mm
    top = h - 20*mm

    c.setFont(FONT_BOLD, 16)
    c.drawString(left, top, TITLE)
    y = top - 10*mm

    c.setFont(FONT_REG, 10)
    order_id = meta.get("order_id","")
    client   = meta.get("customer_name","")
    tel      = meta.get("phone","")
    email    = meta.get("email","")
    created  = meta.get("created_at","")

    c.drawString(left, y, f"Order ID: {order_id}    Client: {client}    Tél: {tel}    Email: {email}")
    y -= 5*mm
    if created:
        c.drawString(left, y, f"Créé le: {created}")
        y -= 5*mm

    # top rule
    c.line(15*mm, y, w - 15*mm, y)
    y -= 7*mm

    # column widths
    MARG_L = 15*mm; MARG_R = 15*mm
    usable_w = w - MARG_L - MARG_R
    COL_PREVIEW = 32*mm
    COL_QTY     = 30*mm
    COL_REMARK  = 45*mm
    COL_PRODUCT = usable_w - (COL_PREVIEW + COL_QTY + COL_REMARK)

    # header labels
    x0 = MARG_L
    c.setFont(FONT_REG, 9)
    c.drawString(x0 + 2*mm,      y, "Aperçu")
    c.drawString(x0 + COL_PREVIEW + 2*mm,                   y, "Produit")
    c.drawString(x0 + COL_PREVIEW + COL_PRODUCT + 2*mm,     y, "Qté")
    c.drawString(x0 + COL_PREVIEW + COL_PRODUCT + COL_QTY + 2*mm, y, "Remarque")

    y -= 3*mm
    c.line(15*mm, y, w - 15*mm, y)
    return y, (MARG_L, usable_w, COL_PREVIEW, COL_PRODUCT, COL_QTY, COL_REMARK)

def build_order_pdf_table(order_data: dict, out_path: str):
    # make sure fonts are ready
    _ensure_fonts()

    c = canvas.Canvas(out_path, pagesize=A4)
    w, h = A4

    y, cols = _draw_header(c, w, h, order_data or {})
    MARG_L, usable_w, COL_PREVIEW, COL_PRODUCT, COL_QTY, COL_REMARK = cols

    items = (order_data or {}).get("items", [])
    MIN_ROW_H = 28*mm            # a bit taller to accommodate fonts
    PREVIEW_MAX_H = 22*mm
    CELL_PAD = 3*mm

    PROD_SIZE = 11
    META_SIZE = 10
    PROD_LEAD = _leading(PROD_SIZE)
    META_LEAD = _leading(META_SIZE)

    def new_page():
        nonlocal y
        c.showPage()
        y, _ = _draw_header(c, w, h, order_data or {})

    for it in items:
        name = (it.get("name") or "").strip()
        q_u  = int(it.get("qty_units") or 0)
        q_c  = int(it.get("qty_cases") or 0)
        upc  = int(it.get("units_per_case") or 0)
        remark = (it.get("remark") or "").strip()

        total_units = (q_u or 0) + (q_c or 0) * (upc or 0)
        qty_lines = []
        if q_c:
            qty_lines.append(pluralize(q_c, "caisse", "caisses"))
        if q_u:
            qty_lines.append(pluralize(q_u, "unité", "unités"))
        if total_units:
            qty_lines.append(f"Total: {total_units} unités")

        prod_lines   = wrap(name, FONT_REG, PROD_SIZE, COL_PRODUCT - 2*CELL_PAD)
        remark_lines = wrap(remark, FONT_REG, META_SIZE, COL_REMARK - 2*CELL_PAD)
        text_h = max(
            len(prod_lines)   * PROD_LEAD + 2*CELL_PAD,
            len(qty_lines)    * META_LEAD + 2*CELL_PAD,
            len(remark_lines) * META_LEAD + 2*CELL_PAD,
            PREVIEW_MAX_H + 2*CELL_PAD
        )
        row_h = max(MIN_ROW_H, text_h)

        # page break
        if y - row_h < 20*mm:
            new_page()

        # column x positions
        x0 = MARG_L
        x1 = x0 + COL_PREVIEW
        x2 = x1 + COL_PRODUCT
        x3 = x2 + COL_QTY
        x4 = x3 + COL_REMARK

        # borders
        c.line(MARG_L, y, x4, y)
        c.line(MARG_L, y - row_h, x4, y - row_h)
        for xx in (x1, x2, x3, x4):
            c.line(xx, y, xx, y - row_h)

        # 1) preview image
        img_path = it.get("image_path")
        if img_path:
            try:
                img = ImageReader(img_path)
                iw, ih = img.getSize()
                box_w = COL_PREVIEW - 2*CELL_PAD
                box_h = PREVIEW_MAX_H
                scale = min(box_w/iw, box_h/ih)
                draw_w = iw * scale
                draw_h = ih * scale
                img_x = x0 + CELL_PAD + (box_w - draw_w)/2
                img_y = y - CELL_PAD - draw_h - (row_h - 2*CELL_PAD - box_h)/2
                c.drawImage(img, img_x, img_y, draw_w, draw_h, preserveAspectRatio=True, mask='auto')
            except Exception:
                c.setLineWidth(0.5)
                c.rect(x0 + CELL_PAD, y - CELL_PAD - PREVIEW_MAX_H,
                       COL_PREVIEW - 2*CELL_PAD, PREVIEW_MAX_H)
        else:
            c.setLineWidth(0.5)
            c.rect(x0 + CELL_PAD, y - CELL_PAD - PREVIEW_MAX_H,
                   COL_PREVIEW - 2*CELL_PAD, PREVIEW_MAX_H)

        # 2) product name
        c.setFont(FONT_REG, PROD_SIZE)
        ty = y - CELL_PAD - PROD_SIZE  # baseline start
        for line in prod_lines:
            c.drawString(x1 + CELL_PAD, ty, line)
            ty -= PROD_LEAD

        # 3) quantities
        c.setFont(FONT_REG, META_SIZE)
        ty = y - CELL_PAD - META_SIZE
        for line in qty_lines:
            c.drawString(x2 + CELL_PAD, ty, line)
            ty -= META_LEAD

        # 4) remarks
        c.setFont(FONT_REG, META_SIZE)
        ty = y - CELL_PAD - META_SIZE
        for line in remark_lines:
            c.drawString(x3 + CELL_PAD, ty, line)
            ty -= META_LEAD

        y -= row_h

    c.save()

# Backward compat
build_order_pdf = build_order_pdf_table
