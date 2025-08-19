import io
from PIL import Image

def normalize_image_bytes(file_bytes: bytes, target_w: int = 800, target_h: int = 600,
                          bg=(245,245,245), out_fmt: str = "JPEG", quality: int = 85) -> bytes:
    """
    等比缩放到不超过 target_w/target_h，然后居中放在固定画布上（不裁剪）。
    最后按 JPEG（或 PNG）压缩，统一尺寸与大小，便于前端显示、存储与生成 PDF。
    """
    im = Image.open(io.BytesIO(file_bytes))
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    elif im.mode == "RGBA":
        bg_img = Image.new("RGB", im.size, bg)
        bg_img.paste(im, mask=im.split()[-1])
        im = bg_img

    im.thumbnail((target_w, target_h), Image.LANCZOS)

    canvas = Image.new("RGB", (target_w, target_h), bg)
    x = (target_w - im.width) // 2
    y = (target_h - im.height) // 2
    canvas.paste(im, (x, y))

    buf = io.BytesIO()
    if out_fmt.upper() == "PNG":
        canvas.save(buf, "PNG", optimize=True)
    else:
        canvas.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()
