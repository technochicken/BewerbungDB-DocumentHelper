"""E-Mail-Entwurf (.eml) erzeugen."""

from __future__ import annotations

import re
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional


def fill_text_placeholders(template: str, context: dict) -> str:
    """{{key}} ersetzen; unbekannte oder leere Schlüssel bleiben sichtbar stehen."""
    def _repl(m: re.Match) -> str:
        val = context.get(m.group(1))
        return str(val) if val not in (None, "") else m.group(0)
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", _repl, template)


def parse_email_template(template: str) -> tuple[Optional[str], str]:
    """Trennt eine optionale 'Betreff:'-Zeile vom Text."""
    lines = template.splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if line.strip().lower().startswith("betreff:"):
            return line.strip()[len("betreff:"):].strip(), "\n".join(lines[i + 1:]).lstrip("\n")
        break
    return None, template


def find_email_template(*dirs: Optional[Path]) -> Optional[str]:
    for d in dirs:
        if not d or not d.exists():
            continue
        for p in sorted(d.glob("blprnt*Email*.txt")):
            try:
                return p.read_text(encoding="utf-8")
            except OSError:
                continue
    return None


def write_eml(
    output_path: Path,
    context: dict,
    absender_email: str,
    pdf_path: Optional[Path] = None,
    template: Optional[str] = None,
) -> Path:
    subject_tpl, body_tpl = parse_email_template(template) if template is not None else (None, None)

    jobtitel = context.get("bereinigter_jobtitel") or context.get("jobtitel") or "Stelle"
    firma = context.get("firma") or ""
    betreff = (
        fill_text_placeholders(subject_tpl, context)
        if subject_tpl is not None
        else f"Bewerbung als {jobtitel}" + (f" bei {firma}" if firma else "")
    )
    body = (
        fill_text_placeholders(body_tpl, context)
        if body_tpl is not None
        else (context.get("anschreiben") or "")
    )

    msg = MIMEMultipart("mixed")
    msg["Subject"] = betreff
    msg["MIME-Version"] = "1.0"
    msg["X-Unsent"] = "1"  # Outlook/Thunderbird öffnen es als neue Nachricht
    if absender_email:
        msg["From"] = absender_email
    if context.get("ansprechpartner_email"):
        msg["To"] = context["ansprechpartner_email"]
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if pdf_path and pdf_path.exists():
        att = MIMEBase("application", "pdf")
        att.set_payload(pdf_path.read_bytes())
        encoders.encode_base64(att)
        att.add_header("Content-Disposition", "attachment", filename=pdf_path.name)
        msg.attach(att)

    output_path.write_bytes(msg.as_bytes())
    return output_path
