# utils/pdf_utils.py
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

TITLE = "Xinya Supermarché — Bon de commande"

# -------- Font selection (Latin vs CJK) --------
FONT_LATIN = "Helvetica"
FONT_LATIN_BOLD = "Helvetica-Bold"
FONT_CJK = None  # will be set to ArialUnicodeMS / Noto/SourceHan / STSong-Light

def _try_register_ttf(name_hint: str, file_candidates):
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
    global FONT_LATIN, FONT_LATIN_BOLD, FONT_CJK
    # 1) Prefer Arial Unicode MS for *both* Latin and CJK if available
    arial = _try_register_ttf("ArialUnicodeMS", [
        "utils/fonts/ArialUnicodeMS.ttf", "utils/fonts/Arial Unicode MS.ttf",
        "assets/fonts/ArialUnicodeMS.ttf", "assets/fonts/Arial Unicode MS.ttf",
        "fonts/ArialUnicodeMS.ttf", "fonts/Arial Unicode MS.ttf",
        "/usr/share/fonts/truetype/arial/ArialUnicodeMS.ttf",
        "/usr/share/fonts/truetype/msfonts/ArialUnicodeMS.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/ArialUnicodeMS.ttf",
    ])
    if arial:
        FONT_LATIN = arial
        FONT_LATIN_BOLD = arial  # this font has no dedicated bold face
        FONT_CJK = arial
        return

    # 2) Try Noto Sans CJK / Source Han Sans for both
    noto = _try_register_ttf("NotoSansSC", [
        "utils/fonts/NotoSansSC-Regular.ttf", "utils/fonts/NotoSansSC-Regular.otf",
        "assets/fonts/NotoSansSC-Regular.ttf", "assets/fonts/NotoSansSC-Regular.otf",
    ])
    if noto:
        # optional bold
        _try_register_ttf("NotoSansSC-Bold", [
            "utils/fonts/NotoSansSC-Bold.ttf", "utils/fonts/NotoSansSC-Bold.otf",
            "assets/fonts/NotoSansSC-Bold.ttf", "assets/fonts/NotoSansSC-Bold.otf",
        ])
        FONT_LATIN = noto
        FONT_LATIN_BOLD = "NotoSansSC-Bold" if "NotoSansSC-Bold" in pdfmetrics.getRegisteredFontNames() else noto
        FONT_CJK = noto
        return

    shs = _try_register_ttf("SourceHanSansSC", [
        "utils/fonts/SourceHanSansSC-Regular.otf",
        "assets/fonts/SourceHanSansSC-Regular.otf",
        "utils/fonts/SourceHanSans-Regular.otf",
        "assets/fonts/SourceHanSans-Regular.otf",
    ])
    if shs:
        _try_register_ttf("SourceHanSansSC-Bold", [
            "utils/fonts/SourceHanSansSC-Bold.otf",
            "assets/fonts/SourceHanSansSC-Bold.otf",
            "utils/fonts/SourceHanSans-Bold.otf",
            "assets/fonts/SourceHanSans-Bold.otf",
        ])
        FONT_LATIN = shs
        FONT_LATIN_BOLD = "SourceHanSansSC-Bold" if "SourceHanSansSC-Bold" in pdfmetrics.getRegisteredFontNames() else shs
        FONT_CJK = shs
        return

    # 3) Fallback: built-in STSong for CJK, Helvetica for Latin
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        FONT_CJK = "STSong-Light"
    except Exception:
        FONT_CJK = "Helvetica"  # worst-case

# ---------- Mixed text rendering & wrapping ----------
def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    # CJK Unified + punctuation ranges
    return (
        0x4E00 <= code <= 0x9FFF or       # CJK Unified Ideographs
        0x3400 <= code <= 0x4DBF or       # Extension A
        0x2000 <= code <= 0x206F or       # General Punctuation
        0x3000 <= code <= 0x303F or       # CJK Symbols and Punctuation
        0xFF00 <= code <= 0xFFEF          # Halfwidth/Fullwidth forms
    )

def wrap_mixed(text: str, size: float, max_w: float):
    # Greedy wrapper that handles CJK (no spaces) and Latin (space separated).
    # Returns list of lines. Preserves existing newlines.
    if not text:
        return []
    lines = []
    cur = ""
    cur_w = 0.0
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur, cur_w = "", 0.0
            continue
        font = FONT_CJK if _is_cjk(ch) else FONT_LATIN
        ch_w = pdfmetrics.stringWidth(ch, font, size)
        if cur_w + ch_w <= max_w or not cur:
            cur += ch
            cur_w += ch_w
        else:
            lines.append(cur.rstrip())
            cur, cur_w = ch, ch_w
    if cur:
        lines.append(cur.rstrip())
    return lines

def draw_text_mixed(c, x: float, y: float, text: str, size: float):
    # Draw a single line with mixed fonts by character, left to right.
    cx = x
    for ch in text:
        font = FONT_CJK if _is_cjk(ch) else FONT_LATIN
        c.setFont(font, size)
        c.drawString(cx, y, ch)
        cx += pdfmetrics.stringWidth(ch, font, size)

def _leading(sz):
    return int(sz * 1.35)

# ---------- Layout ----------
def _draw_header(c, w, h, meta):
    left = 15*mm
    top = h - 20*mm

    c.setFont(FONT_LATIN_BOLD, 16)
    c.drawString(left, top, TITLE)
    y = top - 10*mm

    # meta line(s): pure Latin most of the time
    c.setFont(FONT_LATIN, 10)
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

    c.line(15*mm, y, w - 15*mm, y)
    y -= 7*mm

    MARG_L = 15*mm; MARG_R = 15*mm
    usable_w = w - MARG_L - MARG_R
    COL_PREVIEW = 32*mm
    COL_QTY     = 30*mm
    COL_REMARK  = 45*mm
    COL_PRODUCT = usable_w - (COL_PREVIEW + COL_QTY + COL_REMARK)

    x0 = MARG_L
    c.setFont(FONT_LATIN, 9)
    c.drawString(x0 + 2*mm,      y, "Aperçu")
    c.drawString(x0 + COL_PREVIEW + 2*mm,                   y, "Produit")
    c.drawString(x0 + COL_PREVIEW + COL_PRODUCT + 2*mm,     y, "Qté")
    c.drawString(x0 + COL_PREVIEW + COL_PRODUCT + COL_QTY + 2*mm, y, "Remarque")

    y -= 3*mm
    c.line(15*mm, y, w - 15*mm, y)
    return y, (MARG_L, usable_w, COL_PREVIEW, COL_PRODUCT, COL_QTY, COL_REMARK)

def build_order_pdf_table(order_data: dict, out_path: str):
    _ensure_fonts()

    c = canvas.Canvas(out_path, pagesize=A4)
    w, h = A4

    y, cols = _draw_header(c, w, h, order_data or {})
    MARG_L, usable_w, COL_PREVIEW, COL_PRODUCT, COL_QTY, COL_REMARK = cols

    items = (order_data or {}).get("items", [])
    MIN_ROW_H = 28*mm
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
        remark = (it.get("remark") or "").strip()

        qty_lines = []
        if q_c:
            qty_lines.append(f"{q_c} {'caisse' if q_c == 1 else 'caisses'}")
        if q_u:
            qty_lines.append(f"{q_u} {'unité' if q_u == 1 else 'unités'}")

        # wrapping
        prod_lines   = wrap_mixed(name,   PROD_SIZE, COL_PRODUCT - 2*CELL_PAD)
        remark_lines = wrap_mixed(remark, META_SIZE, COL_REMARK - 2*CELL_PAD)
        text_h = max(
            len(prod_lines)   * PROD_LEAD + 2*CELL_PAD,
            len(qty_lines)    * META_LEAD + 2*CELL_PAD,
            len(remark_lines) * META_LEAD + 2*CELL_PAD,
            PREVIEW_MAX_H + 2*CELL_PAD
        )
        row_h = max(MIN_ROW_H, text_h)

        if y - row_h < 20*mm:
            new_page()

        x0 = MARG_L
        x1 = x0 + COL_PREVIEW
        x2 = x1 + COL_PRODUCT
        x3 = x2 + COL_QTY
        x4 = x3 + COL_REMARK

        c.line(MARG_L, y, x4, y)
        c.line(MARG_L, y - row_h, x4, y - row_h)
        for xx in (x1, x2, x3, x4):
            c.line(xx, y, xx, y - row_h)

        # image
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

        # product name (mixed)
        ty = y - CELL_PAD - PROD_SIZE
        for line in prod_lines:
            draw_text_mixed(c, x1 + CELL_PAD, ty, line, PROD_SIZE)
            ty -= PROD_LEAD

        # qty (Latin)
        c.setFont(FONT_LATIN, META_SIZE)
        ty = y - CELL_PAD - META_SIZE
        for line in qty_lines:
            c.drawString(x2 + CELL_PAD, ty, line)
            ty -= META_LEAD

        # remark (mixed)
        ty = y - CELL_PAD - META_SIZE
        for line in remark_lines:
            draw_text_mixed(c, x3 + CELL_PAD, ty, line, META_SIZE)
            ty -= META_LEAD

        y -= row_h

    c.save()

# Backward compatibility
build_order_pdf = build_order_pdf_table
