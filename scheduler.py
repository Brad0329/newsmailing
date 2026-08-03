"""예약 발송 스케줄러.

구조:
- APScheduler `BackgroundScheduler`를 앱 프로세스 내에서 구동 (별도 워커 없음)
- 상태는 파일(data/scheduled/<id>/)에서 단일 진실 — APScheduler 자체 jobstore는 메모리 전용
- 앱 시작 시 `init()` 호출 → pending 예약 중 미래분은 APScheduler에 재등록, 과거분은 status=missed로 마킹
- 예약 취소 = 폴더 삭제 + job 해제
- 작업 실행 시 meta.json + attachments를 다시 로드 → mailer.send → 성공 시 폴더 삭제, 실패 시 status=failed

운영 전제:
- exe가 실행 중이어야 예약 시각에 발송 가능. 꺼져 있던 시각의 예약은 다음 기동 시 missed로 기록(즉시 발송 안 함).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

import mailer
import storage

_KST = timezone(timedelta(hours=9))
_logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


def _get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        with _lock:
            if _scheduler is None:
                _scheduler = BackgroundScheduler(timezone=_KST)
    return _scheduler


def init() -> None:
    """앱 시작 시 1회 호출. pending 예약 재등록 + 과거분 missed 마킹 + 스케줄러 시작."""
    sched = _get_scheduler()
    if sched.running:
        return

    now = datetime.now(_KST)
    for meta in storage.list_scheduled():
        sid = meta.get("schedule_id")
        if not sid:
            continue
        if meta.get("status") != "pending":
            continue
        run_at = _parse_iso(meta.get("scheduled_at"))
        if run_at is None:
            _logger.warning("schedule %s: invalid scheduled_at, skipping", sid)
            continue
        if run_at <= now:
            # 앱이 꺼져 있던 동안 지나간 예약 — 자동 발송하지 않음
            storage.update_scheduled_status(sid, "missed")
            _logger.info("schedule %s: marked as missed (scheduled_at=%s)", sid, run_at)
            continue
        _add_job(sched, sid, run_at)

    sched.start()
    _logger.info("scheduler started with %d pending jobs", len(sched.get_jobs()))


def shutdown() -> None:
    """앱 종료 시 호출 (선택)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


def register(schedule_id: str, run_at_iso: str) -> None:
    """신규 예약을 APScheduler에 등록."""
    run_at = _parse_iso(run_at_iso)
    if run_at is None:
        raise ValueError(f"예약 시각 형식이 올바르지 않습니다: {run_at_iso}")
    if run_at <= datetime.now(_KST):
        raise ValueError("예약 시각은 현재보다 미래여야 합니다.")
    sched = _get_scheduler()
    if not sched.running:
        sched.start()
    _add_job(sched, schedule_id, run_at)


def cancel(schedule_id: str) -> bool:
    """예약 취소: 폴더 삭제 + job 제거. 성공 여부 반환."""
    sched = _get_scheduler()
    try:
        sched.remove_job(_job_id(schedule_id))
    except Exception:
        pass  # 이미 실행됐거나 등록 안 됨 — 폴더만 정리
    return storage.delete_scheduled(schedule_id)


# ---------- 내부 ----------


def _job_id(schedule_id: str) -> str:
    return f"send_{schedule_id}"


def _add_job(sched: BackgroundScheduler, schedule_id: str, run_at: datetime) -> None:
    sched.add_job(
        _execute,
        trigger=DateTrigger(run_date=run_at),
        args=[schedule_id],
        id=_job_id(schedule_id),
        replace_existing=True,
        misfire_grace_time=300,  # 5분 내 지연 도달하면 실행
    )


def _execute(schedule_id: str) -> None:
    """트리거 시각 도달 → 디스크에서 재로드 후 발송."""
    meta = storage.load_scheduled(schedule_id)
    if not meta or meta.get("status") != "pending":
        _logger.warning("schedule %s: not pending, skip execute", schedule_id)
        return

    try:
        attachments = storage.load_scheduled_attachments(schedule_id)
        recipients = mailer.parse_recipients(meta.get("recipients") or "")
        if not recipients:
            raise ValueError("수신자가 비어 있습니다.")
        sent_count = mailer.send(
            recipients,
            meta.get("subject") or "",
            meta.get("articles") or [],
            intro=meta.get("intro") or "",
            signature=meta.get("signature") or "",
            sender_name=meta.get("sender_name") or "",
            sender_email=meta.get("sender_email") or "",
            html_fragment=meta.get("html_fragment"),
            attachments=attachments,
        )
        storage.append_history(
            subject=meta.get("subject") or "",
            recipients_count=len(recipients),
            sent_count=sent_count,
        )
        # 성공 → 폴더 삭제
        storage.delete_scheduled(schedule_id)
        _logger.info("schedule %s: sent to %d recipients", schedule_id, sent_count)
    except Exception as e:
        _logger.exception("schedule %s: send failed", schedule_id)
        storage.update_scheduled_status(
            schedule_id,
            "failed",
            error=str(e),
            failed_at=datetime.now(_KST).isoformat(timespec="seconds"),
        )


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_KST)
    return dt
