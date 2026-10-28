import smtplib
from email.message import EmailMessage


def send_approved_email(*, host: str, port: int, username: str, password: str,
                        sender_email: str, sender_name: str, recipient: str,
                        subject: str, body: str, postal_address: str, business_name: str = "") -> None:
    if not all((host, username, password, sender_email, recipient, postal_address)):
        raise ValueError("Complete SMTP credentials, sender email, recipient, and postal address first.")
    message = EmailMessage()
    message["From"] = f"{sender_name} <{sender_email}>" if sender_name else sender_email
    message["To"] = recipient
    message["Subject"] = subject
    sender = business_name.strip() or sender_name.strip() or "[Sender]"
    message.set_content(
        f"{body.strip()}\n\nThis is a commercial message from {sender}.\n"
        f"{postal_address.strip()}\n\nIf you don't want further emails, reply 'unsubscribe' and I will not contact you again."
    )
    with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
        smtp.login(username, password)
        smtp.send_message(message)
