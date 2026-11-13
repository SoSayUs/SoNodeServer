import unittest
try:
    import fakeredis
except ImportError:  # dev-only dependency
    fakeredis = None

from rq import Queue, SimpleWorker
from rq.job import JobStatus

from utils.jobs import enqueue_unique, make_job_id


def noop(id=None, **kw):
    return id


class Owner:
    pk = 'o1'
    def work(self, id=None):
        return id


@unittest.skipIf(fakeredis is None, 'fakeredis not installed')
class EnqueueUniqueTests(unittest.TestCase):
    def setUp(self):
        self.conn = fakeredis.FakeStrictRedis()
        self.high = Queue('high', connection=self.conn)
        self.main = Queue('main', connection=self.conn)

    def test_duplicate_skipped_same_queue(self):
        j1, c1 = enqueue_unique(self.high, noop, id='a')
        j2, c2 = enqueue_unique(self.high, noop, id='a')
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(j1.id, j2.id)
        self.assertEqual(len(self.high), 1)

    def test_duplicate_skipped_across_queues(self):
        enqueue_unique(self.high, noop, id='a')
        _, created = enqueue_unique(self.main, noop, id='a')
        self.assertFalse(created)
        self.assertEqual(len(self.main), 0)

    def test_different_identity_not_deduped(self):
        enqueue_unique(self.high, noop, id='a')
        _, created = enqueue_unique(self.high, noop, id='b')
        self.assertTrue(created)
        self.assertEqual(len(self.high), 2)

    def test_explicit_unique_collapses_different_kwargs(self):
        enqueue_unique(self.high, noop, block='obj', unique='blk1')
        _, created = enqueue_unique(self.high, noop, block_id='blk1', unique='blk1')
        self.assertFalse(created)

    def test_finished_job_can_be_requeued(self):
        enqueue_unique(self.high, noop, id='a')
        SimpleWorker([self.high], connection=self.conn).work(burst=True)
        _, created = enqueue_unique(self.high, noop, id='a')
        self.assertTrue(created)
        self.assertEqual(len(self.high), 1)

    def test_started_job_blocks_requeue(self):
        job, _ = enqueue_unique(self.high, noop, id='a')
        self.high.remove(job)
        job.set_status(JobStatus.STARTED)
        _, created = enqueue_unique(self.high, noop, id='a')
        self.assertFalse(created)

    def test_lock_held_skips(self):
        job_id = make_job_id(noop, {'args': (), 'kwargs': {'id': 'a'}})
        self.conn.set(f'sonet:uniq-lock:{job_id}', 'other', ex=10)
        job, created = enqueue_unique(self.high, noop, id='a')
        self.assertIsNone(job)
        self.assertFalse(created)
        self.assertEqual(len(self.high), 0)

    def test_lock_released_after_enqueue(self):
        enqueue_unique(self.high, noop, id='a')
        self.assertEqual(self.conn.keys('sonet:uniq-lock:*'), [])

    def test_bound_method_identity_includes_instance_pk(self):
        o1, o2 = Owner(), Owner()
        o2.pk = 'o2'
        enqueue_unique(self.high, o1.work, id='x')
        _, dup = enqueue_unique(self.high, o1.work, id='x')
        _, other = enqueue_unique(self.high, o2.work, id='x')
        self.assertFalse(dup)
        self.assertTrue(other)

    def test_max_depth_backpressure(self):
        enqueue_unique(self.high, noop, id='a')
        job, created = enqueue_unique(self.high, noop, id='b', max_depth=1)
        self.assertIsNone(job)
        self.assertFalse(created)


if __name__ == '__main__':
    unittest.main()
