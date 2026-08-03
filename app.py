"""newsmailing Flask 엔트리포인트."""
import json
import os
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, render_template, request

import config
import defaults
import mailer
import naver_client
import scheduler
import storage

_KST = timezone(timedelta(hours=9))

app = Flask(__name__)

# 첨부파일 최대 총 크기 25MB (multipart request body 포함)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/history")
def history_page():
    return render_template("history.html")


@app.route("/api/history", methods=["GET"])
def api_history():
    return jsonify({"success": True, "entries": storage.load_history()})


@app.route("/api/mailing-lists", methods=["GET", "POST", "DELETE"])
def api_mailing_lists():
    if request.method == "GET":
        return jsonify({"success": True, "lists": storage.load_mailing_lists()})

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        recipients = data.get("recipients") or ""
        if not name:
            return jsonify({"success": False, "error": "이름이 비어 있습니다."}), 400
        if not recipients.strip():
            return jsonify({"success": False, "error": "수신자 내용이 비어 있습니다."}), 400
        try:
            storage.save_mailing_list(name, recipients)
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        return jsonify({"success": True, "lists": storage.load_mailing_lists()})

    # DELETE
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "삭제할 리스트 이름이 없습니다."}), 400
    ok = storage.delete_mailing_list(name)
    if not ok:
        return jsonify({"success": False, "error": "해당 이름의 리스트를 찾지 못했습니다."}), 404
    return jsonify({"success": True, "lists": storage.load_mailing_lists()})


@app.route("/api/settings", methods=["GET"])
def api_settings():
    saved = storage.load_mail_fields()
    return jsonify(
        {
            "recipients": storage.load_recipients(),
            "keywords": storage.load_keywords(),
            # 저장된 값이 있으면 그대로, 없으면 defaults 사용
            "sender_name_default": saved["sender_name"] or defaults.DEFAULT_SENDER_NAME,
            "sender_email_default": saved["sender_email"] or (config.SMTP_FROM or ""),
            "subject_default": saved["subject"] or defaults.DEFAULT_SUBJECT,
            "intro_default": saved["intro"] or defaults.DEFAULT_INTRO,
            "signature_default": saved["signature"] or defaults.DEFAULT_SIGNATURE,
        }
    )


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(silent=True) or {}
    raw = (data.get("keywords") or "").strip()
    per_keyword = int(data.get("per_keyword") or 5)
    # 검색 기간 (최근 N일, 1~5). 범위 밖 값은 디폴트 2로 보정.
    try:
        days = int(data.get("days") or 2)
    except (TypeError, ValueError):
        days = 2
    if days < 1 or days > 5:
        days = 2

    if not raw:
        return jsonify({"success": False, "error": "검색어가 비어 있습니다."}), 400

    keywords = [k.strip() for k in raw.split(",") if k.strip()]
    if not keywords:
        return jsonify({"success": False, "error": "유효한 검색어가 없습니다."}), 400

    try:
        articles = naver_client.collect(keywords, per_keyword=per_keyword, days=days)
    except config.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"검색 실패: {e}"}), 500

    # 성공 시 입력 원문을 저장 (다음 실행 시 자동 로드)
    storage.save_keywords(raw)

    return jsonify(
        {
            "success": True,
            "articles": [a.to_dict() for a in articles],
        }
    )


@app.route("/api/preview", methods=["POST"])
def api_preview():
    data = request.get_json(silent=True) or {}
    articles = data.get("articles") or []
    intro = data.get("intro") or ""
    signature = data.get("signature") or ""
    if not isinstance(articles, list):
        articles = []
    # articles가 비어 있어도 인트로+서명만으로 미리보기 생성 허용
    fragment = mailer.render_body_fragment(articles, intro, signature)
    return jsonify({"success": True, "html_fragment": fragment, "body_style": mailer._BODY_STYLE})


@app.route("/api/send", methods=["POST"])
def api_send():
    p = _parse_send_payload()
    # articles 비어 있어도 발송 허용 (인트로/본문/서명만으로 메일 작성 가능)
    if not p["subject"]:
        return jsonify({"success": False, "error": "제목이 비어 있습니다."}), 400

    recipients = mailer.parse_recipients(p["recipients_raw"])
    if not recipients:
        return jsonify({"success": False, "error": "유효한 수신자가 없습니다."}), 400

    try:
        sent_count = mailer.send(
            recipients,
            p["subject"],
            p["articles"],
            intro=p["intro"],
            signature=p["signature"],
            sender_name=p["sender_name"],
            sender_email=p["sender_email"],
            html_fragment=p["html_fragment"],
            attachments=p["attachments"],
        )
    except config.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"발송 실패: {e}"}), 500

    # 성공 시 메일 카드 필드 전체 저장 + 발송 내역 기록
    storage.save_recipients(p["recipients_raw"])
    storage.save_mail_fields(
        {
            "sender_name": p["sender_name"],
            "sender_email": p["sender_email"],
            "subject": p["subject"],
            "intro": p["intro"],
            "signature": p["signature"],
        }
    )
    storage.append_history(
        subject=p["subject"],
        recipients_count=len(recipients),
        sent_count=sent_count,
    )

    return jsonify({"success": True, "sent_count": sent_count})


def _parse_send_payload() -> dict:
    """/api/send 와 /api/schedule 가 공통으로 쓰는 payload 파서."""
    is_multipart = (request.content_type or "").startswith("multipart/")
    attachments: list[mailer.Attachment] = []
    if is_multipart:
        f = request.form
        recipients_raw = (f.get("recipients") or "").strip()
        subject = (f.get("subject") or "").strip()
        intro = f.get("intro") or ""
        signature = f.get("signature") or ""
        sender_name = (f.get("sender_name") or "").strip()
        sender_email = (f.get("sender_email") or "").strip()
        html_fragment = f.get("html_fragment")
        scheduled_at = (f.get("scheduled_at") or "").strip()
        try:
            articles = json.loads(f.get("articles") or "[]")
        except json.JSONDecodeError:
            articles = []
        for file in request.files.getlist("attachments"):
            if not file or not file.filename:
                continue
            data_bytes = file.read()
            if not data_bytes:
                continue
            attachments.append((file.filename, data_bytes, file.mimetype or None))
    else:
        data = request.get_json(silent=True) or {}
        recipients_raw = (data.get("recipients") or "").strip()
        subject = (data.get("subject") or "").strip()
        intro = data.get("intro") or ""
        signature = data.get("signature") or ""
        sender_name = (data.get("sender_name") or "").strip()
        sender_email = (data.get("sender_email") or "").strip()
        html_fragment = data.get("html_fragment")
        scheduled_at = (data.get("scheduled_at") or "").strip()
        articles = data.get("articles") or []

    if not isinstance(articles, list):
        articles = []

    return {
        "recipients_raw": recipients_raw,
        "subject": subject,
        "intro": intro,
        "signature": signature,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "html_fragment": html_fragment,
        "scheduled_at": scheduled_at,
        "articles": articles,
        "attachments": attachments,
    }


@app.route("/api/schedule", methods=["POST"])
def api_schedule():
    """미래 시각에 실행될 예약 발송을 저장 + APScheduler 등록."""
    p = _parse_send_payload()
    if not p["subject"]:
        return jsonify({"success": False, "error": "제목이 비어 있습니다."}), 400
    if not p["scheduled_at"]:
        return jsonify({"success": False, "error": "예약 시각이 비어 있습니다."}), 400

    recipients = mailer.parse_recipients(p["recipients_raw"])
    if not recipients:
        return jsonify({"success": False, "error": "유효한 수신자가 없습니다."}), 400

    # 시각 파싱: 브라우저 `datetime-local`은 타임존 없음 → KST로 해석
    try:
        raw_dt = p["scheduled_at"]
        dt = datetime.fromisoformat(raw_dt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_KST)
    except ValueError:
        return jsonify({"success": False, "error": "예약 시각 형식이 올바르지 않습니다."}), 400

    if dt <= datetime.now(_KST) + timedelta(seconds=5):
        return jsonify({"success": False, "error": "예약 시각은 현재보다 미래여야 합니다."}), 400

    scheduled_at_iso = dt.isoformat(timespec="seconds")

    meta = {
        "recipients": p["recipients_raw"],
        "subject": p["subject"],
        "intro": p["intro"],
        "signature": p["signature"],
        "sender_name": p["sender_name"],
        "sender_email": p["sender_email"],
        "html_fragment": p["html_fragment"],
        "articles": p["articles"],
        "scheduled_at": scheduled_at_iso,
    }

    schedule_id = storage.create_scheduled(meta, attachments=p["attachments"])
    try:
        scheduler.register(schedule_id, scheduled_at_iso)
    except Exception as e:
        # 스케줄러 등록 실패 → 저장한 폴더 정리
        storage.delete_scheduled(schedule_id)
        return jsonify({"success": False, "error": f"예약 등록 실패: {e}"}), 500

    # 입력값 저장 (즉시 발송과 동일)
    storage.save_recipients(p["recipients_raw"])
    storage.save_mail_fields(
        {
            "sender_name": p["sender_name"],
            "sender_email": p["sender_email"],
            "subject": p["subject"],
            "intro": p["intro"],
            "signature": p["signature"],
        }
    )

    return jsonify(
        {
            "success": True,
            "schedule_id": schedule_id,
            "scheduled_at": scheduled_at_iso,
            "recipients_count": len(recipients),
        }
    )


@app.route("/api/scheduled", methods=["GET"])
def api_scheduled_list():
    """예약 목록. 각 항목에 최소한의 표시 정보 포함 (첨부 바이너리 제외)."""
    items = storage.list_scheduled()
    # 표시용 투영 — 민감정보는 그대로 두되 UI가 쓰는 필드만 추리지는 않음
    return jsonify({"success": True, "items": items})


@app.route("/api/scheduled/<schedule_id>", methods=["DELETE"])
def api_scheduled_delete(schedule_id: str):
    ok = scheduler.cancel(schedule_id)
    if not ok:
        return jsonify({"success": False, "error": "해당 예약을 찾을 수 없습니다."}), 404
    return jsonify({"success": True})


@app.errorhandler(413)
def too_large(_):
    return jsonify({"success": False, "error": "첨부파일 총 크기가 너무 큽니다 (최대 25MB)."}), 413


def start_scheduler() -> None:
    """앱 구동 시 1회 호출. 테스트 import 시엔 자동 시작하지 않도록 명시적 호출 방식."""
    scheduler.init()


if __name__ == "__main__":
    # Flask debug reloader가 부모 프로세스에서 중복 시작하는 것 방지
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not config.FLASK_DEBUG:
        start_scheduler()
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
