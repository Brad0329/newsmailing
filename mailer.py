"""SMTP HTML 메일 발송."""
from __future__ import annotations

import html
import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import config

# 튜플 형식: (filename: str, data: bytes, content_type: str|None)
Attachment = tuple[str, bytes, "str | None"]


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _render_block(text: str) -> str:
    """여러 줄 텍스트를 HTML로 (줄바꿈 보존)."""
    if not text:
        return ""
    return _esc(text).replace("\n", "<br>")


_BODY_STYLE = (
    "font-family:-apple-system,'Segoe UI','Malgun Gothic',sans-serif; "
    "color:#222; max-width:720px; margin:0; padding:16px;"
)


def render_body_fragment(articles: list[dict], intro: str, signature: str) -> str:
    """`<body>` 내부에 들어갈 컨텐츠 HTML만 반환. 편집 가능한 미리보기에 사용."""
    items = []
    for a in articles:
        title = _esc(a.get("title", ""))
        link = _esc(a.get("link", ""))
        source = _esc(a.get("source", ""))
        items.append(
            f'<p style="margin:12px 0; font-size:15px; line-height:1.7; color:#333;">'
            f'<a href="{link}" target="_blank" rel="noopener" '
            f'style="color:#5D4037; font-weight:bold; text-decoration:underline;">{title}</a>'
            f' / {source}'
            f'</p>'
        )
    articles_html = "\n".join(items) if items else (
        '<p style="color:#888;">기사 없음</p>'
    )
    intro_html = (
        f'<div style="margin:0 0 16px; color:#333; line-height:1.7;">{_render_block(intro)}</div>'
        if intro else ""
    )
    signature_html = (
        f'<div style="margin-top:24px; color:#555; font-size:13px; line-height:1.5;">'
        f'{_render_block(signature)}</div>'
        if signature else ""
    )
    return f"{intro_html}\n{articles_html}\n{signature_html}"


def wrap_document(body_fragment: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="{_BODY_STYLE}">
{body_fragment}
</body>
</html>
"""


def render_html(articles: list[dict], intro: str, signature: str) -> str:
    return wrap_document(render_body_fragment(articles, intro, signature))


def render_text(articles: list[dict], intro: str, signature: str) -> str:
    """HTML 미지원 클라이언트용 plain text 버전."""
    lines = []
    if intro:
        lines.append(intro)
        lines.append("")
    for a in articles:
        lines.append(f"- {a.get('title', '')} / {a.get('source', '')}")
        lines.append(f"  {a.get('link', '')}")
    if signature:
        lines.append("")
        lines.append(signature)
    return "\n".join(lines)


# Backwards-compatible private aliases for existing tests
_render_html = render_html
_render_text = render_text


def parse_recipients(raw: str) -> list[str]:
    """세미콜론 구분 문자열 → 이메일 리스트 (공백/빈값 제거)."""
    if not raw:
        return []
    return [x.strip() for x in raw.split(";") if x.strip()]


def _resolve_from(sender_email: str) -> str:
    """헤더 From 주소 결정. 입력 없으면 SMTP_FROM 사용."""
    v = (sender_email or "").strip()
    return v if v else config.SMTP_FROM


def _guess_content_type(filename: str, fallback: str | None) -> tuple[str, str]:
    if fallback:
        main, _, sub = fallback.partition("/")
        if main and sub:
            return main, sub
    ctype, _ = mimetypes.guess_type(filename)
    if not ctype:
        return "application", "octet-stream"
    main, _, sub = ctype.partition("/")
    return main, (sub or "octet-stream")


def _make_msg(
    recipients: list[str],
    subject: str,
    articles: list[dict],
    intro: str,
    signature: str,
    sender_name: str,
    sender_email: str,
    html_fragment: str | None,
    attachments: list[Attachment] | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    display_name = sender_name.strip() if sender_name and sender_name.strip() else "newsmailing"
    from_addr = _resolve_from(sender_email)
    msg["From"] = formataddr((display_name, from_addr))
    msg["To"] = from_addr  # 실제 수신자는 BCC
    msg["Reply-To"] = from_addr
    domain = (from_addr or "localhost").split("@", 1)[-1]
    msg["Message-ID"] = make_msgid(domain=domain)
    msg.set_content(render_text(articles, intro, signature))
    html_body = (
        wrap_document(html_fragment)
        if html_fragment is not None and html_fragment.strip()
        else render_html(articles, intro, signature)
    )
    msg.add_alternative(html_body, subtype="html")
    for filename, data, ctype in attachments or []:
        if not filename or not data:
            continue
        maintype, subtype = _guess_content_type(filename, ctype)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return msg


def send(
    recipients: list[str],
    subject: str,
    articles: list[dict],
    intro: str = "",
    signature: str = "",
    sender_name: str = "",
    sender_email: str = "",
    html_fragment: str | None = None,
    attachments: list[Attachment] | None = None,
) -> int:
    """수신자 전원에게 BCC로 단일 발송. 발송된 수신자 수 반환.

    envelope(MAIL FROM)은 항상 인증 계정(SMTP_FROM)을 사용 — 바운스 처리 및 SPF 정합성.
    헤더 From은 sender_email이 비어있지 않으면 그것, 아니면 SMTP_FROM.
    """
    config.check_smtp()

    if not recipients:
        raise ValueError("수신자가 비어 있습니다.")
    if not subject:
        raise ValueError("제목이 비어 있습니다.")

    msg = _make_msg(recipients, subject, articles, intro, signature, sender_name, sender_email, html_fragment, attachments)

    context = ssl.create_default_context()
    to_addrs = [config.SMTP_FROM, *recipients]
    if config.SMTP_USE_TLS:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(config.SMTP_USER, config.SMTP_PASS)
            smtp.send_message(msg, from_addr=config.SMTP_FROM, to_addrs=to_addrs)
    else:
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=context, timeout=30) as smtp:
            smtp.login(config.SMTP_USER, config.SMTP_PASS)
            smtp.send_message(msg, from_addr=config.SMTP_FROM, to_addrs=to_addrs)

    return len(recipients)
