
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
def build_order_pdf(order_data: dict, out_path: str):
    c = canvas.Canvas(out_path, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20*mm, h-20*mm, "Xinya Supermarché — Bon de commande")
    c.setFont("Helvetica", 10)
    y = h - 30*mm
    c.drawString(20*mm, y, f"Order ID: {order_data.get('order_id','')}  |  Client: {order_data.get('customer_name','')}  |  Email: {order_data.get('email','')}")
    y -= 10*mm
    c.line(15*mm, y, w-15*mm, y); y -= 5*mm
    for i, it in enumerate(order_data.get("items", []), start=1):
        if y < 40*mm:
            c.showPage(); y = h - 20*mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20*mm, y, f"{i}. {it.get('name','')}"); y -= 5*mm
        c.setFont("Helvetica", 10)
        q_u = int(it.get("qty_units",0) or 0)
        q_c = int(it.get("qty_cases",0) or 0)
        upc = int(it.get("units_per_case",0) or 0)
        line = []
        if q_u>0: line.append(f"{q_u} unités")
        if q_c>0: line.append(f"{q_c} caisses")
        if upc and q_c>0: line.append(f"Total {q_u + q_c*upc} unités")
        c.drawString(20*mm, y, " | ".join(line)); y -= 5*mm
        if it.get("remark"):
            c.drawString(20*mm, y, f"Note: {it['remark']}"); y -= 5*mm
        imgp = it.get("image_path")
        if imgp:
            try:
                c.drawImage(ImageReader(imgp), 20*mm, y-25*mm, width=40*mm, height=30*mm, preserveAspectRatio=True, anchor='sw')
            except:
                pass
        y -= 30*mm
    c.save()
