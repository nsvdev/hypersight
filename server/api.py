import datetime as dt
import json
import os
from uuid import uuid4

from cv2 import cv2
from flask import request, abort, send_from_directory, Blueprint, current_app
from sqlalchemy import func, desc

from server.models import Camera, TrafficCounter, ObjectsCounter, ProcessorEvent, DT_FORMAT

api_bp = Blueprint('api', __name__, url_prefix='/')


@api_bp.route('/statusWatch', methods=['GET'])
def status_watch():
    """
    Loop through all cameras in DB and return True if corresponding watcher is active (process exists)
    :return:
    """
    result = {}
    # noinspection PyUnresolvedReferences
    cameras = Camera.query.all()
    celery = None
    inspector = celery.control.inspect()
    active_tasks = inspector.active()
    for camera in cameras:
        result[camera.id] = {'watching': False, 'url': camera.stream_url}
        if active_tasks:
            for usr, tasks in inspector.active().items():
                for task in tasks:
                    if 'watch_camera' in task['name'] and task['kwargs'].get('camera_id', None) == camera.id:
                        result[camera.id]['watching'] = True
                        break
    result['err'] = False
    return json.dumps(result)


@api_bp.route('/Traffic', methods=['POST'])
def get_traffic():
    """
    Calculates passed by traffic for some interval
    - proc_id: processor id
    - start_ts: timestamp to start from
    - stop_ts: [Optional] last timestamp; if omitted - current ts is used
    ts format: "2020-02-23 14:00:00.0"
    """
    params = request.get_json()
    proc_id = params.get('proc_id', None)
    if not proc_id:
        abort(400, 'proc_id is required')
    start_ts = params.get('start_ts', None)
    if not start_ts:
        abort(400, 'start_ts is required')
    stop_ts = params.get('stop_ts', dt.datetime.now())
    # noinspection PyUnresolvedReferences
    processor = TrafficCounter.query.filter_by(id=proc_id).first()
    if processor:
        # noinspection PyUnresolvedReferences
        res = ProcessorEvent.query.with_entities(func.sum(ProcessorEvent.value).label("traffic"),
                                                 func.min(ProcessorEvent.ts).label("min_ts"),
                                                 func.max(ProcessorEvent.ts).label("max_ts")).filter_by(
            processor_id=processor.id).filter(ProcessorEvent.ts <= stop_ts).filter(ProcessorEvent.ts > start_ts).first()
        if res.traffic:
            return {'traffic': int(res.traffic),
                    'min_ts': res.min_ts.strftime(DT_FORMAT),
                    'max_ts': res.max_ts.strftime(DT_FORMAT),
                    'err': False}
        else:
            return {'err': True, 'msg': 'No records found'}
    else:
        return {'err': True, 'msg': 'Wrong processor id'}


@api_bp.route('/Objects', methods=['POST'])
def get_objects():
    """
    Calculates number oj objects at frame at given timestamp
    Returns number of objects at frame ROEs at latest ts not exceeding the given ts

    - proc_id: processor id
    - ts: [Optional] timestamp; if omitted - current ts is used
    ts format: "2020-02-23 14:00:00.0"
    """
    params = request.get_json()
    proc_id = params.get('proc_id', None)
    if not proc_id:
        abort(400, 'proc_id is required')
    ts = params.get('ts', dt.datetime.now())
    # noinspection PyUnresolvedReferences
    processor = ObjectsCounter.query.filter_by(id=proc_id).first()
    if processor:
        # noinspection PyUnresolvedReferences
        res = ProcessorEvent.query.filter_by(processor_id=processor.id).filter(ProcessorEvent.ts <= ts).order_by(
            desc(ProcessorEvent.ts)).first()
        if res:
            return {'count': int(res.value),
                    'ts': res.ts.strftime(DT_FORMAT),
                    'err': False}
        else:
            return {'err': True, 'msg': 'No observations found'}
    else:
        return {'err': True, 'msg': 'Wrong processor id'}


@api_bp.route('/getFrame', methods=['POST'])
def get_frame():
    """
    Requests one frame from camera, saves it to temp dir and returns path to it.
    To avoid overfill it removes old frames from temp dir
    """
    params = request.get_json()
    camera_id = params.get('camera_id', None)
    if not camera_id:
        return abort(400, 'camera_id is required')
    # find camera
    # noinspection PyUnresolvedReferences
    camera = Camera.query.get(camera_id)
    # read frame
    if camera.stream_url.isnumeric():
        # web cam has url like 0, 1 2 etc
        cap = cv2.VideoCapture(int(camera.stream_url))
    else:
        cap = cv2.VideoCapture(camera.stream_url)
    ret, frame = cap.read()
    cap.release()
    if ret:
        os.makedirs(current_app.config['FRAMES_PATH'], exist_ok=True)
        # remove old frames
        now = dt.datetime.now()
        for fn in os.listdir(current_app.config['FRAMES_PATH']):
            fp = os.path.join(current_app.config['FRAMES_PATH'], fn)
            if os.stat(fp).st_mtime < (now - dt.timedelta(minutes=1)).timestamp():
                if os.path.isfile(fp):
                    os.remove(fp)
        # save frame to the disk
        fn = str(uuid4()) + '.jpg'
        fp = os.path.join(current_app.config['FRAMES_PATH'], fn)
        cv2.imwrite(fp, frame)
        # send image parameters
        h, w, _ = frame.shape
        return {'path': '/frame/' + fn, 'height': h, 'width': w, 'err': False}
    else:
        return {'err': True, 'msg': 'Camera does not respond'}


# Custom static data
@api_bp.route('/frame/<path:filename>')
def custom_static(filename):
    return send_from_directory(current_app.config['FRAMES_PATH'], filename)


# preview video files
@api_bp.route('/videos/<path:filename>')
def preview_hls(filename):
    return send_from_directory(current_app.config['PROCESSORS_PREVIEW_DIR'], filename, cache_timeout=-1)


@api_bp.route('/badrequest400')
def bad_request():
    abort(400)
