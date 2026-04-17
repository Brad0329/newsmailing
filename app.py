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


@app.route("/api/settings", methods=["GET"])
def api_settings():
    return jsonify(
        {
            "recipients": storage.load_recipients(),
            "sender_name_default": defaults.DEFAULT_SENDER_NAME,
            "sender_email_default": config.SMTP_FROM or "",
            "subject_default": defaults.DEFAULT_SUBJECT,
            "intro_default": defaults.DEFAULT_INTRO,
            "signature_default": defaults.DEFAULT_SIGNATURE,
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

    # 성공 시 수신자 목록 저장
    storage.save_recipients(recipients_raw)

    return jsonify({"success": True, "sent_count": sent_count})


@app.errorhandler(413)
def too_large(_):
    return jsonify({"success": False, "error": "첨부파일 총 크기가 너무 큽니다 (최대 25MB)."}), 413


if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
