import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import calendar_utils

def _parse_bool(val: str | None, default: bool = True) -> bool:
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}

def _get_smtp_config():
    """Resolve SMTP/SES configuration from environment variables.

    Supports both new MAIL_* (SES-style) and legacy SMTP_* variables.
    - Auth username is taken from MAIL_USERNAME or SMTP_USERNAME (not the From email)
    - From header is MAIL_DEFAULT_SENDER or SENDER_EMAIL
    """
    server = (
        os.environ.get("MAIL_SERVER")
        or os.environ.get("SMTP_SERVER")
        or "smtp.gmail.com"
    )
    port = int(
        os.environ.get("MAIL_PORT")
        or os.environ.get("SMTP_PORT")
        or 587
    )
    use_tls = _parse_bool(os.environ.get("MAIL_USE_TLS"), default=True)

    smtp_username = (
        os.environ.get("MAIL_USERNAME")
        or os.environ.get("SMTP_USERNAME")
        or os.environ.get("SENDER_EMAIL", "")
    )
    smtp_password = (
        os.environ.get("MAIL_PASSWORD")
        or os.environ.get("SENDER_PASSWORD")
        or ""
    )

    from_email = (
        os.environ.get("MAIL_DEFAULT_SENDER")
        or os.environ.get("SENDER_EMAIL")
        or "notifications@popinmeet.com"
    )

    app_domain = os.environ.get(
        "APP_DOMAIN",
        os.environ.get("REPLIT_DEV_DOMAIN", "localhost")
    )

    return {
        "server": server,
        "port": port,
        "use_tls": use_tls,
        "username": smtp_username,
        "password": smtp_password,
        "from_email": from_email,
        "app_domain": app_domain,
    }

def _send_email(to_email: str, subject: str, plain_body: str, attachments: list[tuple[str, bytes, str]] | None = None, html_body: str | None = None) -> bool:
    """Generic email sender using resolved SMTP config.

    attachments: list of tuples (filename, content_bytes, mime_subtype)
    where mime type is ('text', mime_subtype). For ICS use ('text','calendar').
    """
    try:
        cfg = _get_smtp_config()

        # If no password, log and return success (dry run)
        if not cfg["password"]:
            print(f"=== EMAIL (dry-run) to {to_email} ===")
            print(f"Subject: {subject}")
            print(plain_body)
            print("=== END EMAIL ===")
            return True

        # Outer message with mixed content (text/html + attachments)
        msg = MIMEMultipart('mixed')
        msg['From'] = cfg["from_email"]
        msg['To'] = to_email
        msg['Subject'] = subject
        # Create alternative part to include both plain text and HTML
        alternative = MIMEMultipart('alternative')
        alternative.attach(MIMEText(plain_body, 'plain'))
        if html_body:
            alternative.attach(MIMEText(html_body, 'html'))
        msg.attach(alternative)

        # Attachments
        if attachments:
            for filename, content_bytes, mime_subtype in attachments:
                part = MIMEBase('text', mime_subtype)
                part.set_payload(content_bytes)
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                msg.attach(part)

        server = smtplib.SMTP(cfg["server"], cfg["port"])
        if cfg["use_tls"]:
            server.starttls()
        server.login(cfg["username"], cfg["password"])
        server.sendmail(cfg["from_email"], to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_confirmation_email(organizer_email, organizer_name, meeting_title, best_slot, available_people, meeting_token, meeting_timezone='US/Mountain', start_utc: str | None = None, end_utc: str | None = None):
    """Send confirmation email to organizer when meeting time is confirmed"""
    try:
        cfg = _get_smtp_config()
        app_domain = cfg["app_domain"]

        # Build add-to-calendar URLs (prefer canonical UTCs when provided)
        google_url = calendar_utils.get_google_calendar_url(meeting_title, best_slot, timezone=meeting_timezone, start_utc=start_utc, end_utc=end_utc) or ""
        # Remove Outlook personal; use Outlook 365 link and label it as Outlook
        outlook365_url = calendar_utils.get_outlook365_calendar_url(meeting_title, best_slot, timezone=meeting_timezone, start_utc=start_utc, end_utc=end_utc) or ""

        # Plaintext fallback
        body = f"""
Hi {organizer_name},

Great news! Your meeting "{meeting_title}" has been confirmed.

🗓️ CONFIRMED TIME:
{best_slot}

👥 PARTICIPANTS AVAILABLE:
{', '.join(available_people)} ({len(available_people)} people)

📊 View full summary:
https://{app_domain}/meeting/{meeting_token}/summary

Add to Calendar:
• Google Calendar: {google_url}
• Outlook: {outlook365_url}
• Download .ics: Attached universal calendar file

Thank you for using POPin Meet!

Best regards,
The POPin Meet Team
"""

        # HTML body with buttons
        # Use simple table-based buttons compatible with most email clients
        html_body = f"""
<html>
  <body style="font-family: Arial, sans-serif; color: #222;">
    <p>Hi {organizer_name},</p>
    <p>Great news! Your meeting "<strong>{meeting_title}</strong>" has been confirmed.</p>
    <p>
      <strong>🗓️ Confirmed Time:</strong><br/>
      {best_slot}
    </p>
    <p>
      <strong>👥 Participants Available:</strong><br/>
      {', '.join(available_people)} ({len(available_people)} people)
    </p>
    <p><strong>📊 View full summary:</strong><br/>
      <a href="https://{app_domain}/meeting/{meeting_token}/summary" target="_blank">https://{app_domain}/meeting/{meeting_token}/summary</a>
    </p>

    <h3 style="margin-top:24px;">Add to Calendar</h3>
    <table role="presentation" cellspacing="0" cellpadding="0" style="margin: 12px 0;">
      <tr>
        <td style="padding-right:8px;">
          <a href="{google_url}" target="_blank" style="background-color:#0d6efd;color:#ffffff;text-decoration:none;padding:10px 14px;border-radius:4px;display:inline-block;font-size:14px;">
            <span style="font-weight:600;">Google Calendar</span>
          </a>
        </td>
        <td style="padding-right:8px;">
          <a href="{outlook365_url}" target="_blank" style="background-color:#0dcaf0;color:#000000;text-decoration:none;padding:10px 14px;border-radius:4px;display:inline-block;font-size:14px;">
            <span style="font-weight:600;">Outlook</span>
          </a>
        </td>
        <td>
          <a href="https://{app_domain}/meeting/{meeting_token}/download-ics" target="_blank" style="background-color:#198754;color:#ffffff;text-decoration:none;padding:10px 14px;border-radius:4px;display:inline-block;font-size:14px;">
            <span style="font-weight:600;">Download .ics</span>
          </a>
        </td>
      </tr>
    </table>

    <p style="margin-top:24px;">Thank you for using POPin Meet!</p>
    <p>Best regards,<br/>The POPin Meet Team</p>
  </body>
</html>
"""

        attachments = []
        ics_content = calendar_utils.create_ics_calendar(
            meeting_title,
            organizer_name,
            best_slot,
            timezone=meeting_timezone,
            organizer_email=organizer_email,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        if ics_content:
            filename = f"{meeting_title.replace(' ', '_')}.ics"
            attachments.append((filename, ics_content.encode(), 'calendar'))

        return _send_email(
            to_email=organizer_email,
            subject=f"Meeting Confirmed: {meeting_title}",
            plain_body=body,
            attachments=attachments,
            html_body=html_body,
        )
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def should_send_confirmation_email(token, current_best_slot):
    """Check if we should send a confirmation email based on meeting state"""
    # For now, we'll send an email whenever there's a clear best time slot
    # In the future, we could track if we've already sent a confirmation for this meeting
    return current_best_slot is not None

def send_participant_response_notification(organizer_email, organizer_name, meeting_title, respondent_name, meeting_token):
    """Send notification to organizer when someone responds"""
    try:
        cfg = _get_smtp_config()
        app_domain = cfg["app_domain"]

        body = f"""
Hi {organizer_name},

{respondent_name} just responded to your meeting poll for "{meeting_title}".

📊 View updated responses and availability:
https://{app_domain}/meeting/{meeting_token}/summary

Best regards,
The POPin Meet Team
"""

        return _send_email(
            to_email=organizer_email,
            subject=f"New Response: {meeting_title}",
            plain_body=body,
        )
    except Exception as e:
        print(f"Error sending response notification: {e}")
        return False