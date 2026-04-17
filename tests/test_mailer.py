"""mailer 순수 함수 테스트 (SMTP 연결 없음)."""
import mailer


def test_parse_recipients_basic():
    assert mailer.parse_recipients("a@x.com; b@x.com") == ["a@x.com", "b@x.com"]


def test_parse_recipients_trims_whitespace():
    assert mailer.parse_recipients("  a@x.com  ;b@x.com  ;") == ["a@x.com", "b@x.com"]


def test_parse_recipients_empty():
    assert mailer.parse_recipients("") == []
    assert mailer.parse_recipients("   ") == []
    assert mailer.parse_recipients(";;;") == []


def test_render_html_contains_article():
    html_body = mailer._render_html(
        [{"title": "카드 보안", "link": "https://x.com/1", "source": "한스경제"}],
        intro="오늘의 클리핑",
    )
    assert "카드 보안" in html_body
    assert 'href="https://x.com/1"' in html_body
    assert "한스경제" in html_body
    assert "오늘의 클리핑" in html_body


def test_render_html_escapes_user_input():
    html_body = mailer._render_html(
        [{"title": "<script>alert(1)</script>", "link": "https://x.com/1", "source": "src"}],
        intro="",
    )
    assert "<script>" not in html_body
    assert "&lt;script&gt;" in html_body


def test_render_text():
    text = mailer._render_text(
        [{"title": "제목A", "link": "https://x.com/a", "source": "출처1"}],
        intro="안녕",
    )
    assert "안녕" in text
    assert "제목A" in text
    assert "출처1" in text
    assert "https://x.com/a" in text
