
# 这个文件是占位符。如果你的项目根目录已有 utils/email_utils.py，
# 可以把其中的 send_email_with_attachment 复制过来，或直接修改导入路径。
import smtplib, os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

def send_email_with_attachment(subject, body, to_addrs, file_paths):
    host = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    port = int(os.getenv("EMAIL_PORT", "587"))
    use_tls = str(os.getenv("EMAIL_USE_TLS", "true")).lower() == "true"
    user = os.getenv("EMAIL_USER")
    pwd = os.getenv("EMAIL_PASS")

    if not (user and pwd):
        raise RuntimeError("EMAIL_USER / EMAIL_PASS not set")

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(to_addrs if isinstance(to_addrs, (list, tuple)) else [to_addrs])
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for p in file_paths or []:
        with open(p, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(p))
            part["Content-Disposition"] = f'attachment; filename="{os.path.basename(p)}"'
            msg.attach(part)

    smtp = smtplib.SMTP(host, port, timeout=30)
    if use_tls:
        smtp.starttls()
    smtp.login(user, pwd)
    smtp.send_message(msg)
    smtp.quit()
