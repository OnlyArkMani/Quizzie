import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings


def send_email(to_email: str, subject: str, html_body: str):
    """
    Send an HTML email via SMTP (TLS).
    If SMTP_USERNAME is not configured, logs to console and skips sending.
    Call via FastAPI BackgroundTasks so it doesn't block request handling.
    """
    if not settings.SMTP_USERNAME:
        print(f"[EMAIL SKIPPED — SMTP not configured]")
        print(f"  To      : {to_email}")
        print(f"  Subject : {subject}")
        return

    from_addr = settings.EMAIL_FROM or settings.SMTP_USERNAME
    sender    = f"{settings.EMAIL_FROM_NAME} <{from_addr}>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = to_email
    msg.attach(MIMEText(html_body, "html"))

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(sender, to_email, msg.as_string())
        print(f"[EMAIL SENT] To: {to_email} | Subject: {subject}")
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send to {to_email}: {e}")


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

def _base_template(title: str, body_html: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{title}</title>
    </head>
    <body style="margin:0;padding:0;background:#f4f4f5;font-family:Arial,Helvetica,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td align="center" style="padding:40px 16px;">
            <table width="560" cellpadding="0" cellspacing="0"
                   style="background:#ffffff;border-radius:12px;overflow:hidden;
                          box-shadow:0 2px 8px rgba(0,0,0,.08);">
              <!-- Header -->
              <tr>
                <td style="background:#4f46e5;padding:32px 40px;text-align:center;">
                  <h1 style="margin:0;color:#ffffff;font-size:26px;letter-spacing:1px;">
                    🎓 Quizzie
                  </h1>
                </td>
              </tr>
              <!-- Body -->
              <tr>
                <td style="padding:36px 40px;color:#374151;font-size:15px;line-height:1.7;">
                  {body_html}
                </td>
              </tr>
              <!-- Footer -->
              <tr>
                <td style="background:#f9fafb;padding:20px 40px;text-align:center;
                           color:#9ca3af;font-size:12px;border-top:1px solid #e5e7eb;">
                  © 2024 Quizzie · You're receiving this because you signed up at Quizzie.
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """


def _cta_button(href: str, label: str, color: str = "#4f46e5") -> str:
    return f"""
    <p style="text-align:center;margin:28px 0;">
      <a href="{href}"
         style="background:{color};color:#ffffff;padding:14px 32px;border-radius:8px;
                text-decoration:none;font-size:15px;font-weight:bold;display:inline-block;">
        {label}
      </a>
    </p>
    <p style="text-align:center;font-size:12px;color:#9ca3af;">
      Button not working? Copy and paste this link:<br/>
      <a href="{href}" style="color:#4f46e5;word-break:break-all;">{href}</a>
    </p>
    """


# ---------------------------------------------------------------------------
# Public send functions
# ---------------------------------------------------------------------------

def send_verification_email(to_email: str, full_name: str, token: str):
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    body = f"""
    <h2 style="margin:0 0 16px;color:#111827;">Hi {full_name}, welcome to Quizzie! 👋</h2>
    <p>Thanks for signing up. Please verify your email address to activate your account.</p>
    {_cta_button(link, "Verify My Email")}
    <p style="font-size:13px;color:#6b7280;">
      ⏰ This link expires in <strong>24 hours</strong>.<br/>
      If you didn't create an account, you can safely ignore this email.
    </p>
    """
    send_email(to_email, "Verify your Quizzie account", _base_template("Verify Email", body))


def send_password_reset_email(to_email: str, full_name: str, token: str):
    link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    body = f"""
    <h2 style="margin:0 0 16px;color:#111827;">Password Reset Request</h2>
    <p>Hi <strong>{full_name}</strong>,</p>
    <p>We received a request to reset your Quizzie password. Click below to choose a new one:</p>
    {_cta_button(link, "Reset My Password", "#dc2626")}
    <p style="font-size:13px;color:#6b7280;">
      ⏰ This link expires in <strong>1 hour</strong>.<br/>
      If you didn't request a reset, no action is needed — your password remains unchanged.
    </p>
    """
    send_email(to_email, "Reset your Quizzie password", _base_template("Reset Password", body))
