
# utils/pdf_utils.py
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics

TITLE = "Xinya Supermarché — Bon de commande"

# 帮助函数：按宽度换行
def wrap(text, font, size, max_w):
    if not text:
        return []
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(test, font, size) <= max_w:
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
    except:
        return f"{n} {plur}"
    return f"{n} {sing if n == 1 else plur}"

def _draw_header(c, w, h, meta):
    left = 15*mm
    top = h - 20*mm

    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, top, TITLE)
    y = top - 8*mm

    c.setFont("Helvetica", 10)
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

    # 表头分隔线
    c.line(15*mm, y, w - 15*mm, y)
    y -= 7*mm

    # 表头（Aperçu / Produit / Qté / Remarque）
    MARG_L = 15*mm; MARG_R = 15*mm
    usable_w = w - MARG_L - MARG_R
    COL_PREVIEW = 32*mm
    COL_QTY     = 30*mm
    COL_REMARK  = 45*mm
    COL_PRODUCT = usable_w - (COL_PREVIEW + COL_QTY + COL_REMARK)

    x0 = MARG_L
    c.setFont("Helvetica", 9)
    c.drawString(x0 + 2*mm,      y, "Aperçu")
    c.drawString(x0 + COL_PREVIEW + 2*mm,                   y, "Produit")
    c.drawString(x0 + COL_PREVIEW + COL_PRODUCT + 2*mm,     y, "Qté")
    c.drawString(x0 + COL_PREVIEW + COL_PRODUCT + COL_QTY + 2*mm, y, "Remarque")

    # 表头下方的横线
    y -= 3*mm
    c.line(15*mm, y, w - 15*mm, y)
    return y, (MARG_L, usable_w, COL_PREVIEW, COL_PRODUCT, COL_QTY, COL_REMARK)

def build_order_pdf_table(order_data: dict, out_path: str):
    """
    生成“缩略图/商品/数量/备注”四列的表格版 PDF
    order_data 结构预期：
      {
        "order_id": "...",
        "customer_name": "...",
        "phone": "...",
        "email": "...",
        "created_at": "...",
        "items": [
           {"name": "...", "qty_units": 0, "qty_cases": 1, "units_per_case": 12,
            "remark": "...", "image_path": "/path/to/img.jpg"},
           ...
        ]
      }
    """
    c = canvas.Canvas(out_path, pagesize=A4)
    w, h = A4

    y, cols = _draw_header(c, w, h, order_data or {})
    MARG_L, usable_w, COL_PREVIEW, COL_PRODUCT, COL_QTY, COL_REMARK = cols

    items = (order_data or {}).get("items", [])
    MIN_ROW_H = 26*mm            # 行最小高度
    PREVIEW_MAX_H = 22*mm        # 缩略图最大高
    CELL_PAD = 3*mm
    LINE_H = 5.2  # 每行文本的行高（pt）

    def new_page():
        nonlocal y
        c.showPage()
        y, _ = _draw_header(c, w, h, order_data or {})

    for it in items:
        # 先准备各列文本
        name = (it.get("name") or "").strip()
        q_u  = int(it.get("qty_units") or 0)
        q_c  = int(it.get("qty_cases") or 0)
        upc  = int(it.get("units_per_case") or 0)
        remark = (it.get("remark") or "").strip()

        # 数量列：与截图一致，显示 “X caisses” + “Total: Y unités”
        total_units = (q_u or 0) + (q_c or 0) * (upc or 0)
        qty_lines = []
        if q_c:
            qty_lines.append(pluralize(q_c, "caisse", "caisses"))
        if q_u:
            qty_lines.append(pluralize(q_u, "unité", "unités"))
        if total_units:
            qty_lines.append(f"Total: {total_units} unités")

        # 文本换行，计算所需高度
        prod_lines   = wrap(name, "Helvetica", 11, COL_PRODUCT - 2*CELL_PAD)
        remark_lines = wrap(remark, "Helvetica", 10, COL_REMARK - 2*CELL_PAD)

        text_h = max(
            len(prod_lines)   * LINE_H + 2*CELL_PAD,
            len(qty_lines)    * LINE_H + 2*CELL_PAD,
            len(remark_lines) * LINE_H + 2*CELL_PAD,
            PREVIEW_MAX_H + 2*CELL_PAD
        )
        row_h = max(MIN_ROW_H, text_h)

        # 分页：不足一行就翻页（留出底部 20mm）
        if y - row_h < 20*mm:
            new_page()

        # 当前行矩形框（四周分隔线，只画上下横线与列竖线，视觉与截图一致）
        x0 = MARG_L
        x1 = x0 + COL_PREVIEW
        x2 = x1 + COL_PRODUCT
        x3 = x2 + COL_QTY
        x4 = x3 + COL_REMARK

        # 上下横线
        c.line(MARG_L, y, x4, y)
        c.line(MARG_L, y - row_h, x4, y - row_h)
        # 列分隔竖线
        for xx in (x1, x2, x3, x4):
            c.line(xx, y, xx, y - row_h)

        # 绘制各列内容 -----------------------------------
        # 1) 预览图
        img_path = it.get("image_path")
        if img_path:
            try:
                img = ImageReader(img_path)
                iw, ih = img.getSize()
                # 计算缩放，保持比例，放进 (COL_PREVIEW - 2*PAD, PREVIEW_MAX_H)
                box_w = COL_PREVIEW - 2*CELL_PAD
                box_h = PREVIEW_MAX_H
                scale = min(box_w/iw, box_h/ih)
                draw_w = iw * scale
                draw_h = ih * scale
                img_x = x0 + CELL_PAD + (box_w - draw_w)/2
                img_y = y - CELL_PAD - draw_h - (row_h - 2*CELL_PAD - box_h)/2
                c.drawImage(img, img_x, img_y, draw_w, draw_h, preserveAspectRatio=True, mask='auto')
            except Exception:
                # 读不到就画一个灰框占位
                c.setLineWidth(0.5)
                c.rect(x0 + CELL_PAD, y - CELL_PAD - PREVIEW_MAX_H,
                       COL_PREVIEW - 2*CELL_PAD, PREVIEW_MAX_H)

        # 2) 商品名（左对齐）
        c.setFont("Helvetica", 11)
        ty = y - CELL_PAD - 12  # 文字顶线到基线的估计偏移
        for line in prod_lines:
            c.drawString(x1 + CELL_PAD, ty, line)
            ty -= LINE_H

        # 3) 数量列（右侧中列，按行写）
        c.setFont("Helvetica", 10)
        ty = y - CELL_PAD - 12
        for line in qty_lines:
            c.drawString(x2 + CELL_PAD, ty, line)
            ty -= LINE_H

        # 4) 备注列
        c.setFont("Helvetica", 10)
        ty = y - CELL_PAD - 12
        for line in remark_lines:
            c.drawString(x3 + CELL_PAD, ty, line)
            ty -= LINE_H

        # 行间距
        y -= row_h

    c.save()
