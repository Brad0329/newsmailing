"""newsmailing Flask 엔트리포인트."""
import json

from flask import Flask, jsonify, render_template, request

import config
import defaults
import mailer
import naver_client
import storage

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

    if not raw:
        return jsonify({"success": False, "error": "검색어가 비어 있습니다."}), 400

    keywords = [k.strip() for k in raw.split(",") if k.strip()]
    if not keywords:
        return jsonify({"success": False, "error": "유효한 검색어가 없습니다."}), 400

    try:
        articles = naver_client.collect(keywords, per_keyword=per_keyword)
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
    if not isinstance(articles, list) or not articles:
        return jsonify({"success": False, "error": "선택된 기사가 없습니다."}), 400
    fragment = mailer.render_body_fragment(articles, intro, signature)
    return jsonify({"success": True, "html_fragment": fragment, "body_style": mailer._BODY_STYLE})


@app.route("/api/send", methods=["POST"])
def api_send():
    # multipart(첨부 있는 경우)와 JSON(첨부 없는 경우) 양쪽 지원
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
        articles = data.get("articles") or []

    if not isinstance(articles, list) or not articles:
        return jsonify({"success": False, "error": "선택된 기사가 없습니다."}), 400
    if not subject:
        return jsonify({"success": False, "error": "제목이 비어 있습니다."}), 400

    recipients = mailer.parse_recipients(recipients_raw)
    if not recipients:
        return jsonify({"success": False, "error": "유효한 수신자가 없습니다."}), 400

    try:
        sent_count = mailer.send(
            recipients,
            subject,
            articles,
            intro=intro,
            signature=signature,
            sender_name=sender_name,
            sender_email=sender_email,
            html_fragment=html_fragment,
            attachments=attachments,
        )
    except config.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"발송 실패: {e}"}), 500

    # 성공 시 메일 카드 필드 전체 저장 + 발송 내역 기록
    storage.save_recipients(recipients_raw)
    storage.save_mail_fields(
        {
            "sender_name": sender_name,
            "sender_email": sender_email,
            "subject": subject,
            "intro": intro,
            "signature": signature,
        }
    )
    storage.append_history(
        subject=subject,
        recipients_count=len(recipients),
        sent_count=sent_count,
    )

    return jsonify({"success": True, "sent_count": sent_count})


@app.errorhandler(413)
def too_large(_):
    return jsonify({"success": False, "error": "첨부파일 총 크기가 너무 큽니다 (최대 25MB)."}), 413


if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
