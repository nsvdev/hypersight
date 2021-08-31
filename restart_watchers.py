import logging

from celery_worker import celery
from server.models import Camera
from server.tasks import watch_camera

# stop running watchers (if they exist)
logging.info('Stopping all active camera watchers')
inspector = celery.control.inspect()
active_tasks = inspector.active()
if active_tasks:
    for usr, tasks in inspector.active().items():
        for task in tasks:
            if 'watch_camera' in task['name']:
                celery.control.revoke(task['id'], terminate=True, signal='SIGKILL')
                logging.info('Stopped pid {} with args {}'.format(task['worker_pid'], task['kwargs']))
logging.info('Done')

# run new watchers
logging.info('Starting new camera watchers')
# noinspection PyUnresolvedReferences
cams = Camera.query.all()
for cam in cams:
    watch_camera.delay(camera_id=cam.id)
logging.info('Done')
