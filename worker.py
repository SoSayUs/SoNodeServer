
import sys
import multiprocessing

if sys.platform == "darwin":
    multiprocessing.set_start_method("spawn", force=True)

import os

import redis
from rq import Worker, Queue, connections
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sonet.settings")
if __name__ == '__main__':
    django.setup()


listen = ['high', 'main', 'low', 'chat', 'super']

redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')

conn = redis.from_url(redis_url)


if __name__ == '__main__':
    with connections.Connection(conn):
        worker = Worker(map(Queue, listen))
        worker.work()


