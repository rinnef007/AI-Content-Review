from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

from redis import Redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STREAM = os.getenv("JOB_QUEUE_STREAM", "content-review:jobs")
DEAD_STREAM = os.getenv("JOB_QUEUE_DEAD_STREAM", "content-review:jobs:dead")
GROUP = os.getenv("JOB_QUEUE_GROUP", "content-review-workers")
MAX_ATTEMPTS = int(os.getenv("JOB_QUEUE_MAX_ATTEMPTS", "3"))
JOB_TTL = int(os.getenv("JOB_QUEUE_TTL", "86400"))


def redis_client() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_key(job_id: str) -> str:
    return f"content-review:job:{job_id}"


def ensure_group(client: Redis) -> None:
    try:
        client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def enqueue(payload: dict) -> dict:
    client = redis_client()
    ensure_group(client)
    job_id = str(uuid4())
    job = {"id": job_id, "status": "queued", "attempts": 0, "max_attempts": MAX_ATTEMPTS, "created_at": now(), "updated_at": now(), "payload": json.dumps(payload, ensure_ascii=False)}
    client.hset(job_key(job_id), mapping=job)
    client.expire(job_key(job_id), JOB_TTL)
    client.xadd(STREAM, {"job_id": job_id})
    return deserialize(job)


def deserialize(data: dict) -> dict:
    result = dict(data)
    for key in ("attempts", "max_attempts"):
        if key in result:
            result[key] = int(result[key])
    if "payload" in result and isinstance(result["payload"], str):
        result["payload"] = json.loads(result["payload"])
    if "result" in result and isinstance(result["result"], str):
        result["result"] = json.loads(result["result"])
    return result


def get_job(job_id: str) -> dict | None:
    data = redis_client().hgetall(job_key(job_id))
    return deserialize(data) if data else None


def update_job(job_id: str, **fields) -> None:
    fields["updated_at"] = now()
    client = redis_client()
    encoded = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)) for k, v in fields.items()}
    client.hset(job_key(job_id), mapping=encoded)
    client.expire(job_key(job_id), JOB_TTL)


def process_jobs(handler) -> None:
    client = redis_client()
    ensure_group(client)
    consumer = os.getenv("JOB_QUEUE_CONSUMER", f"worker-{uuid4().hex[:8]}")
    while True:
        messages = client.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=1, block=5000)
        for _, entries in messages:
            for message_id, fields in entries:
                job_id = fields["job_id"]
                job = get_job(job_id)
                if not job:
                    client.xack(STREAM, GROUP, message_id)
                    continue
                attempts = job["attempts"] + 1
                update_job(job_id, status="processing", attempts=attempts)
                try:
                    result = handler(job["payload"])
                    update_job(job_id, status="completed", result=result)
                    client.xack(STREAM, GROUP, message_id)
                except Exception as exc:
                    if attempts < MAX_ATTEMPTS:
                        update_job(job_id, status="retrying", error=str(exc))
                        client.xadd(STREAM, {"job_id": job_id})
                    else:
                        update_job(job_id, status="failed", error=str(exc))
                        client.xadd(DEAD_STREAM, {"job_id": job_id, "error": str(exc), "attempts": str(attempts)})
                    client.xack(STREAM, GROUP, message_id)
        time.sleep(0.05)
