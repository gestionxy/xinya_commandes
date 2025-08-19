
import os
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

BASE_DIR = Path(__file__).resolve().parent.parent

def try_register_font():
    font_path = os.getenv("FONT_PATH","").strip()
    candidates = []
    if font_path and os.path.isfile(font_path):
        candidates.append(font_path)
    fonts_dir = BASE_DIR / "assets" / "fonts"
    if fonts_dir.is_dir():
        for fn in fonts_dir.iterdir():
            if fn.suffix.lower() in (".ttf",".otf",".ttc"):
                candidates.append(str(fn))
    common_windows = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\simsun.ttf",
    ]
    candidates.extend([p for p in common_windows if os.path.isfile(p)])
    for p in candidates:
        try:
            pdfmetrics.registerFont(TTFont("CJK", p))
            return "CJK"
        except Exception:
            continue
    return "Helvetica"

def wrap_text(text, font_name, font_size, max_width, c):
    if not text: return [""]
    words = list(text)
    lines, line = [], ""
    for ch in words:
        test = line + ch
        if c.stringWidth(test, font_name, font_size) <= max_width:
            line = test
        else:
            if line: lines.append(line)
            line = ch
    if line: lines.append(line)
    return lines

def draw_centered_lines(c, lines, x_center, y_center, font_name, font_size, line_height):
    c.setFont(font_name, font_size)
    total_h = line_height * len(lines)
    start_y = y_center + (total_h/2) - font_size
    for i, line in enumerate(lines):
        w = c.stringWidth(line, font_name, font_size)
        c.drawString(x_center - w/2, start_y - i*line_height, line)

def build_order_pdf(order_data: dict, output_path: str) -> str:
    page_w, page_h = A4
    c = canvas.Canvas(output_path, pagesize=A4)
    font_name = try_register_font()

    margin_x = 15 * mm
    margin_y = 15 * mm
    y = page_h - margin_y

    c.setFont(font_name, 18)
    c.drawString(margin_x, y, "Xinya Supermarché — Bon de commande")
    y -= 12 * mm

    c.setFont(font_name, 11)
    c.drawString(margin_x, y, f"Order ID: {order_data.get('order_id','')}")
    y -= 6 * mm
    c.drawString(margin_x, y, f"Client: {order_data.get('customer_name','')}   Tél: {order_data.get('phone','')}   Email: {order_data.get('email','')}")
    y -= 6 * mm
    c.drawString(margin_x, y, f"Créé le: {order_data.get('created_at','')}")
    y -= 8 * mm

    c.setFont(font_name, 12)
    c.drawString(margin_x, y, "Aperçu")
    c.drawString(margin_x + 35*mm, y, "Produit")
    c.drawString(margin_x + 105*mm, y, "Qté")
    c.drawString(margin_x + 120*mm, y, "Remarque")
    y -= 4 * mm
    c.line(margin_x, y, page_w - margin_x, y)
    y -= 4 * mm

    rows_per_page = 6
    row_h = 35 * mm
    img_w = 28 * mm
    img_h = 28 * mm

    col_img_x = margin_x
    col_img_w = 32 * mm
    col_prod_x = margin_x + 35 * mm
    col_prod_w = 65 * mm
    col_qty_x = margin_x + 105 * mm
    col_qty_w = 30 * mm
    col_rem_x = col_qty_x + col_qty_w + 5*mm
    col_rem_w = page_w - margin_x - col_rem_x

    items = order_data.get("items", [])

    def draw_page_rows(start_idx):
        nonlocal y
        rows = items[start_idx:start_idx+rows_per_page]
        for i, item in enumerate(rows):
            top_y = y - i*row_h
            bottom_y = top_y - row_h
            c.setLineWidth(0.3)
            c.rect(margin_x, bottom_y, page_w - 2*margin_x, row_h, stroke=1, fill=0)
            row_mid_y = bottom_y + row_h/2

            img_center_x = col_img_x + col_img_w/2
            img_path = item.get("image_path")
            if img_path:
                img_path = str((BASE_DIR / img_path).resolve()) if not os.path.isabs(img_path) else img_path
            if img_path and os.path.isfile(img_path):
                try:
                    c.drawImage(ImageReader(img_path), img_center_x - img_w/2, row_mid_y - img_h/2, width=img_w, height=img_h, preserveAspectRatio=True, anchor='sw', mask='auto')
                except Exception:
                    c.rect(img_center_x - img_w/2, row_mid_y - img_h/2, img_w, img_h, stroke=1, fill=0)
            else:
                c.rect(img_center_x - img_w/2, row_mid_y - img_h/2, img_w, img_h, stroke=1, fill=0)

            name = item.get("name","")
            lines = wrap_text(name, font_name, 11, col_prod_w, c)
            draw_centered_lines(c, lines, col_prod_x + col_prod_w/2, row_mid_y, font_name, 11, 12)

            q_units = int(item.get("qty_units", 0) or 0)
            q_cases = int(item.get("qty_cases", 0) or 0)
            upc = int(item.get("units_per_case", 0) or 0)
            qty_lines = []
            if q_units > 0: qty_lines.append(f"{q_units} unités")
            if q_cases > 0: qty_lines.append(f"{q_cases} caisses")
            if q_units > 0 or q_cases > 0:
                total_units = q_units + (q_cases * upc if upc else 0)
                if upc and q_cases>0:
                    qty_lines.append(f"Total: {total_units} unités")
            draw_centered_lines(c, qty_lines or [""], col_qty_x + col_qty_w/2, row_mid_y, font_name, 10, 11)

            remark = item.get("remark","")
            lines_r = wrap_text(remark, font_name, 10, col_rem_w-4, c)
            draw_centered_lines(c, lines_r, col_rem_x + col_rem_w/2, row_mid_y, font_name, 10, 11)

        y = bottom_y - 8

    if not items:
        draw_page_rows(0)
    else:
        total_pages = (len(items) + rows_per_page - 1) // rows_per_page
        idx = 0
        for p in range(total_pages):
            draw_page_rows(idx)
            idx += rows_per_page
            if p < total_pages - 1:
                c.showPage()
                y = page_h - margin_y
                c.setFont(font_name, 18)
                c.drawString(margin_x, y, "Xinya Supermarché — Bon de commande (suite)")
                y -= 12*mm
                c.setFont(font_name, 12)
                c.drawString(margin_x, y, "Aperçu")
                c.drawString(margin_x + 35*mm, y, "Produit")
                c.drawString(margin_x + 105*mm, y, "Qté")
                c.drawString(margin_x + 120*mm, y, "Remarque")
                y -= 4 * mm
                c.line(margin_x, y, page_w - margin_x, y)
                y -= 4 * mm

    c.showPage()
    c.save()
    return output_path
