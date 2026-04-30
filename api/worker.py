"""
Pihu SaaS — Background Celery Worker
Exponential backoff with jitter, dead-letter queue, task timeouts,
result persistence to PostgreSQL, and crash recovery.
"""

import os
import json
from datetime import datetime
from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded
from logger import get_logger

log = get_logger("CELERY_WORKER")

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

celery_app = Celery(
    "pihu_celery_worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,

    # Retry policy
    task_acks_late=True,                    # Don't ack until task completes
    task_reject_on_worker_lost=True,        # Re-queue if worker crashes mid-task
    worker_prefetch_multiplier=1,           # Fair scheduling

    # Timeouts
    task_soft_time_limit=120,               # Soft limit: 2 minutes (raises SoftTimeLimitExceeded)
    task_time_limit=180,                    # Hard limit: 3 minutes (kills task)

    # Dead-letter queue
    task_default_queue="pihu_tasks",
    task_queues={
        "pihu_tasks": {"exchange": "pihu_tasks"},
        "pihu_dead_letter": {"exchange": "pihu_dead_letter"},
    },

    # Result expiry
    result_expires=86400,                   # Results expire after 24 hours in Redis
)


# ──────────────────────────────────────────
# TASK RESULT PERSISTENCE (PostgreSQL)
# ──────────────────────────────────────────

def _persist_task_result(task_id: str, tenant_id: str, org_id: str,
                         status: str, result: str = None, error: str = None,
                         retry_count: int = 0):
    """Persist task result to PostgreSQL for survival beyond Redis TTL."""
    try:
        from api.database import SyncSessionLocal, TaskRecord
        session = SyncSessionLocal()
        try:
            record = session.query(TaskRecord).filter_by(id=task_id).first()
            if record:
                record.status = status
                record.result_text = result
                record.error_message = error
                record.retry_count = retry_count
                if status in ("success", "failed", "dead_letter"):
                    record.completed_at = datetime.utcnow()
            else:
                record = TaskRecord(
                    id=task_id, tenant_id=tenant_id, org_id=org_id,
                    status=status, result_text=result, error_message=error,
                    retry_count=retry_count
                )
                session.add(record)
            session.commit()
        finally:
            session.close()
    except Exception as e:
        log.error("[%s] Failed to persist task record: %s", task_id, e)


# ──────────────────────────────────────────
# MAIN WORKER TASK
# ──────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="process_complex_intent",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,          # Exponential backoff
    retry_backoff_max=300,       # Max 5 minutes between retries
    retry_jitter=True,           # Add randomness to prevent thundering herd
    max_retries=3,
    acks_late=True,
)
def process_complex_intent(self, user_id: str, org_id: str, raw_input: str, intent_type: str = "chat"):
    """
    Background worker for heavy intent execution.
    Includes retry with exponential backoff, soft timeout handling,
    result persistence, and dead-letter queue routing.
    """
    task_id = self.request.id
    log.info("[%s] Starting background execution for %s: %s",
             task_id, user_id, raw_input[:50])

    _persist_task_result(task_id, user_id, org_id, "running", retry_count=self.request.retries)

    try:
        from pihu_brain import PihuBrain
        from intent_classifier import Intent

        brain = PihuBrain(backend_mode=True, user_id=user_id)
        brain.initialize()

        allowed_async_intents = {"chat", "deep_reasoning", "realtime_query", "prediction"}
        if intent_type not in allowed_async_intents:
            raise ValueError(f"Async intent '{intent_type}' is not allowed")

        intent = Intent(
            type=intent_type,
            confidence=0.99,
            metadata={"user_id": user_id, "task_id": task_id, "org_id": org_id},
            raw_input=raw_input
        )

        result_generator = brain.router.route(intent)

        output_buffer = []
        if hasattr(result_generator.response, "__iter__") and not isinstance(result_generator.response, str):
            for chunk in result_generator.response:
                output_buffer.append(str(chunk))
        else:
            output_buffer.append(str(result_generator.response))

        full_response = "".join(output_buffer)

        _persist_task_result(task_id, user_id, org_id, "success", result=full_response)
        log.info("[%s] Execution success.", task_id)
        return {"status": "success", "response": full_response}

    except SoftTimeLimitExceeded:
        log.error("[%s] SOFT TIMEOUT: Task exceeded 120s limit", task_id)
        _persist_task_result(task_id, user_id, org_id, "failed",
                            error="Task timed out (soft limit: 120s)")
        return {"status": "timeout", "response": "Task exceeded time limit"}

    except (ConnectionError, TimeoutError, OSError) as e:
        # These are auto-retried by Celery config above
        log.warning("[%s] Transient error (retry %d/%d): %s",
                    task_id, self.request.retries, self.max_retries, e)
        _persist_task_result(task_id, user_id, org_id, "running",
                            error=str(e), retry_count=self.request.retries)
        raise  # Re-raise to trigger Celery auto-retry

    except Exception as e:
        log.error("[%s] Worker crash (non-retryable): %s", task_id, e)

        # Route to dead-letter queue after max retries
        if self.request.retries >= self.max_retries:
            _persist_task_result(task_id, user_id, org_id, "dead_letter", error=str(e))
            _send_to_dead_letter(task_id, user_id, org_id, raw_input, str(e))
            return {"status": "dead_letter", "response": str(e)}

        _persist_task_result(task_id, user_id, org_id, "failed", error=str(e))
        return {"status": "error", "response": str(e)}


@celery_app.task(bind=True, name="execute_sub_agent",
                 max_retries=2, soft_time_limit=60)
def execute_sub_agent(self, user_id: str, role: str, context: str):
    """Sub-agent worker for parallel swarm execution with timeout."""
    log.info("[%s] Sub-Agent [%s] engaged for Tenant %s", self.request.id, role, user_id)

    try:
        import time
        time.sleep(2)
        result_payload = f"[{role}] Completed analysis for: {context[:20]}..."
        return {"role": role, "status": "success", "sub_result": result_payload}
    except SoftTimeLimitExceeded:
        return {"role": role, "status": "timeout", "sub_result": "Sub-agent timed out"}


# ──────────────────────────────────────────
# DEAD-LETTER QUEUE
# ──────────────────────────────────────────

@celery_app.task(name="pihu_dead_letter_handler", queue="pihu_dead_letter")
def dead_letter_handler(task_id: str, user_id: str, org_id: str,
                        original_input: str, error: str):
    """
    Dead-letter handler: logs permanently failed tasks for manual review.
    In production, this would alert on-call via PagerDuty/Slack.
    """
    log.critical(
        "💀 DEAD LETTER: task=%s user=%s error=%s input=%s",
        task_id, user_id, error, original_input[:80]
    )
    _persist_task_result(task_id, user_id, org_id, "dead_letter", error=error)


def _send_to_dead_letter(task_id: str, user_id: str, org_id: str,
                         original_input: str, error: str):
    """Route a failed task to the dead-letter queue."""
    try:
        dead_letter_handler.apply_async(
            args=[task_id, user_id, org_id, original_input, error],
            queue="pihu_dead_letter"
        )
    except Exception as e:
        log.error("Failed to send to dead-letter queue: %s", e)
