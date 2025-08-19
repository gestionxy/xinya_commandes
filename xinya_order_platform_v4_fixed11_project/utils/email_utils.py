import os, smtplib, ssl, mimetypes
from email.message import EmailMessage
def send_email_with_attachment(subject: str, body: str, to_emails: list, attachment_paths: list):
    host = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    port = int(os.getenv("EMAIL_PORT", "587"))
    use_tls = str(os.getenv("EMAIL_USE_TLS", "true")).lower() in ("1","true","yes")
    user = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    if not user or not password:
        raise RuntimeError("EMAIL_USER / EMAIL_PASS not set. Fill .env or environment variables.")
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = ", ".join([e for e in to_emails if e])
    msg["Subject"] = subject
    msg.set_content(body)
    for path in attachment_paths or []:
        if not os.path.isfile(path):
            continue
        ctype, encoding = mimetypes.guess_type(path)
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        with open(path, "rb") as fp:
            msg.add_attachment(fp.read(), maintype=maintype, subtype=subtype, filename=os.path.basename(path))
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port) as server:
        if use_tls:
            server.starttls(context=context)
        server.login(user, password)
        server.send_message(msg)
