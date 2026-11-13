"""
Unique job enqueueing for RQ.

Replaces the exists_in_worker() scan + enqueue() pattern, which scanned every worker/queue
on each call and was racy (check, then enqueue, with nothing between).

A job's identity is (function name, identity value) -> deterministic job_id, so the lookup is a
single Redis hash read and is queue-agnostic (a job queued on 'high' blocks a duplicate on 'main').
RQ itself does NOT reject a duplicate job_id (it would queue a second copy and overwrite the first's
args), so check-and-enqueue is serialized with a short per-id Redis lock.

Only jobs that are queued / started / scheduled / deferred count as duplicates. A finished or failed
job with the same id is replaced by the new one.
"""
import hashlib
import json
import uuid

from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus

ACTIVE_STATUSES = {JobStatus.QUEUED, JobStatus.STARTED, JobStatus.SCHEDULED, JobStatus.DEFERRED}
_LOCK_TTL = 10  # seconds; only needs to cover one fetch + enqueue


def _queue(queue):
    if isinstance(queue, str):
        import django_rq  # lazy: lets this module be used/tested without Django settings
        return django_rq.get_queue(queue)
    return queue


def job_name(func):
    return getattr(func, '__qualname__', None) or getattr(func, '__name__', None) or str(func)


def make_job_id(func, unique):
    payload = json.dumps(unique, sort_keys=True, default=str)
    return f"uniq-{job_name(func)}-{hashlib.sha1(payload.encode()).hexdigest()[:24]}"  # RQ ids may not contain ":"


def enqueue_unique(queue, func, *args, unique=None, job_timeout=60, result_ttl=7200, max_depth=None, **kwargs):
    """
    Enqueue func unless an active job with the same identity exists (on any queue).

    unique:    identity of the job (any JSON-able value, e.g. a block id). Defaults to all args/kwargs,
               plus the instance pk when func is a bound model method. Pass it explicitly when callers
               reach the same logical job with different kwargs (block= vs block_id=).
    max_depth: optional backpressure; skip (don't enqueue) when the queue already holds this many jobs.

    Returns (job, created). created is False if skipped as a duplicate, or if another process is
    enqueueing the same id right now (job is None in that case).
    """
    queue = _queue(queue)
    conn = queue.connection

    if unique is None:
        unique = {'args': args, 'kwargs': kwargs}
        owner = getattr(func, '__self__', None)
        if owner is not None and getattr(owner, 'pk', None) is not None:
            unique['self'] = str(owner.pk)
    job_id = make_job_id(func, unique)

    if max_depth is not None and queue.count >= max_depth:
        return None, False

    lock_key = f"sonet:uniq-lock:{job_id}"
    token = uuid.uuid4().hex
    if not conn.set(lock_key, token, nx=True, ex=_LOCK_TTL):
        return None, False  # someone else is enqueueing this exact job right now
    try:
        try:
            existing = Job.fetch(job_id, connection=conn)
            if existing.get_status(refresh=True) in ACTIVE_STATUSES:
                return existing, False
        except NoSuchJobError:
            pass
        job = queue.enqueue(func, *args, job_id=job_id, job_timeout=job_timeout, result_ttl=result_ttl, **kwargs)
        return job, True
    finally:
        held = conn.get(lock_key)
        if held is not None and (held.decode() if isinstance(held, bytes) else held) == token:
            conn.delete(lock_key)
