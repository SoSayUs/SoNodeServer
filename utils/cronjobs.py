

import django_rq
import datetime

from network.models import script_created_modifiable_models
from utils.models import prnt, now_utc


runTimes = {
    'daily_summarizer' : 500,
    'send_notifications' : 200,
    'check_elections': 200,
    'updateTop': 200,
}

functions = [
    {'date' : ['x'], 'dayOfWeek' : ['x'], 'hour' : [8], 'cmds' : ['daily_summarizer', 'check_elections']},
    {'date' : ['x'], 'dayOfWeek' : ['x'], 'hour' : [12], 'cmds' : ['check_elections']},
    {'date' : ['x'], 'dayOfWeek' : ['x'], 'hour' : [18], 'cmds' : ['send_notifications','check_elections']},
    {'date' : ['x'], 'dayOfWeek' : ['x'], 'hour' : [24], 'cmds' : ['check_elections']},

]

def remove_old_modded_items():
    from utils.models import get_model
    for m in script_created_modifiable_models:
        model = get_model(m)
        objs = model.objects.exclude(proposed_modification=None).filter(last_update__lte=now_utc() - datetime.timedelta(days=5))
        if objs:
            for obj in objs:
                super(get_model(obj.objType), obj).delete()

def task_runner():
    print('-------task_runner',now_utc())
    from .models import tasker
    queue = django_rq.get_queue('high')
    queue.enqueue(tasker, now_utc(), job_timeout=300)

def clear_chrome():
    import subprocess, signal
    import os
    try:
        p = subprocess.Popen(['pgrep', '-l' , 'chrome'], stdout=subprocess.PIPE)
        out, err = p.communicate()
        for line in out.splitlines():        
            line = bytes.decode(line)
            pid = int(line.split(None, 1)[0])
            os.kill(pid, signal.SIGKILL)
    except Exception as e:
        prnt('clear chrome fail 1', str(e))
    try:
        subprocess.call(["pkill", "-f", "Google Chrome for Testing"])
    except Exception as e:
        prnt('clear chrome fail 2', str(e))
    try:
        subprocess.call(["pkill", "-f", "chrome_crashpad_handler"])
    except Exception as e:
        prnt('clear chrome fail 3', str(e))
    try:
        subprocess.call(["pkill", "-f", "chrome"])
    except Exception as e:
        prnt('clear chrome fail 4', str(e))
    try:
        subprocess.call(["pkill", "-f", "chromedriver"])
    except Exception as e:
        prnt('clear chrome fail 5', str(e))


def clear_old_jobs():
    import django_rq
    from rq.registry import FailedJobRegistry

    queue_names = ['main', 'high', 'low', 'chat', 'super']

    for queue_name in queue_names:
        connection = django_rq.get_connection(queue_name)
        failed_registry = FailedJobRegistry(queue_name, connection=connection)

        n = 0
        for job_id in reversed(failed_registry.get_job_ids()):
            n += 1
            if n > 500:
                try:
                    failed_registry.remove(job_id, delete_job=True)
                except:
                    # failed jobs expire in the queue. There's a
                    # chance this will raise NoSuchJobError
                    pass

