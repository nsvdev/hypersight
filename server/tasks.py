import datetime as dt
import json
import logging
import os
import signal
import time
import traceback
from typing import List, Tuple
from urllib.error import URLError
from urllib.request import urlopen

import m3u8
import numpy as np
import requests
from celery import Celery
from cv2 import cv2

from server.database import db_session
from server.instance.config import OBJECT_DETECTOR_URL, SEGMENTS_DIR
from server.models import Camera, DetectedObject, Frame, Processor

celery = Celery(__name__, autofinalize=False)


class GracefulKiller:
    """
    OS signals listener. Used for flawless exit by OS demand
    """
    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.kill_now = True


def combine_images(images: List[np.ndarray], grid_size: tuple):
    """
    Combine images to specified frame as a grid (mosaic)
    :param images:
    :param grid_size:
    :return:
    """
    if len(images) != grid_size[0] * grid_size[1]:
        logging.error('Grid size {} is not aligned with images list {}'.format(grid_size, len(images)))
        raise ValueError
    rows = []
    for i in range(0, len(images), grid_size[1]):
        rows.append(cv2.hconcat(images[i:i + grid_size[1]]))
    return cv2.vconcat(rows)


def offset(obj: list, x_offset: float, y_offset: float, grid_size: Tuple[int, int]):
    """
    Returns obj coordinates shifted by x_offset and y_offset.
    :param obj:
    :param x_offset:
    :param y_offset:
    :param grid_size:
    :return:
    """
    return [(obj[0] - x_offset) * grid_size[1], (obj[1] - y_offset) * grid_size[0],
            (obj[2] - x_offset) * grid_size[1], (obj[3] - y_offset) * grid_size[0]] + obj[4:]


def detect_objs(frames: List[Frame], grid_size: Tuple[int, int]):
    """
    Batch object detection. Combines frame into one grid mosaic, sends them to detection server and unpacks results.
    :param frames:
    :param grid_size:
    :return:
    """
    content_type = 'image/jpeg'
    headers = {'content-type': content_type}
    batch_size = grid_size[0] * grid_size[1]
    for i in range(0, len(frames), batch_size):
        sub_frames = frames[i: i + batch_size]
        if len(sub_frames) < batch_size:
            # add empty frames when batch is nod even
            # (for example there were 15 frames and batch_size =2 =>
            # last frame goes alone => 1 empty frame must be added)
            h, w, _ = sub_frames[0].image.shape
            batch_image = combine_images([f.image for f in sub_frames] +
                                         [np.zeros((h, w, 3), dtype=np.uint8)] * (batch_size - len(sub_frames)),
                                         grid_size)
        else:
            batch_image = combine_images([f.image for f in sub_frames], grid_size)

        # request server for detection
        _, buf = cv2.imencode('.jpg', batch_image)
        r = requests.post(OBJECT_DETECTOR_URL, data=buf.tostring(), headers=headers)
        objects = json.loads(r.text)

        # split objects by initial frames
        frame_id = 0
        for row in range(grid_size[0]):
            for col in range(grid_size[1]):
                x_min = col / grid_size[1]
                x_max = x_min + 1 / grid_size[1]
                y_min = row / grid_size[0]
                y_max = y_min + 1 / grid_size[0]
                if frame_id < len(sub_frames):
                    # to avoid writing objects of empty frames (which do not exist)
                    f_objs = [offset(obj, x_min, y_min, grid_size) for obj in objects if
                              x_min <= obj[0] <= x_max and y_min <= obj[1] <= y_max]
                    logging.debug('Detected {} objects at {} frame'.format(len(f_objs), frame_id))
                    sub_frames[frame_id].objects = [DetectedObject(*obj) for obj in f_objs]
                frame_id += 1


@celery.task
def watch_camera(camera_id: int):
    """
    Camera watcher. It is spawned as a separate process. One process is watching for one camera.
    It does full cycle of processing:
    - downloading
    - object detection
    - processors analysis
    - DB saving

    After each loop it check DB again for possible changes (processor on/off, roe changes etc).
    If no processors selected or camera is unavailable it sleeps for some time and starts the loop again.

    """
    reconnect_time = 5  # seconds
    max_attempts_to_dl_segment = 10

    # temp directory for storing downloaded ts files
    camera_tmp_dir = os.path.join(SEGMENTS_DIR, str(camera_id))
    if not os.path.exists(camera_tmp_dir):
        os.makedirs(camera_tmp_dir)

    # storage of last processed segment urls
    last_processed_segments = []

    # OS signals listener
    killer = GracefulKiller()

    # find camera
    # noinspection PyUnresolvedReferences
    camera = Camera.query.filter_by(id=camera_id).first()
    if camera:
        logging.info('Camera {} found.'.format(camera.id))
    else:
        logging.error('Camera {} was not found in DB. Aborted.'.format(camera.id))
        return

    while True:
        # rollback session to reload all camera and processor parameters from DB
        db_session.rollback()
        # check system events
        if killer.kill_now:
            logging.warning("Camera {} watch process was terminated by signal".format(camera.id))
            return

        # list of processors that must process frames
        enabled_procs: List[Processor] = [p for p in camera.processors if p.enabled]
        if enabled_procs:
            logging.info('{} processors will be applied'.format(len(enabled_procs)))
        else:
            logging.warning('No enabled processors found for camera {}'.format(camera.id))
            logging.warning('Sleeping for {} seconds'.format(reconnect_time))
            time.sleep(reconnect_time)
            continue
        # logging.info('Refresh session each attempt')
        # db.session.commit()
        # db.session.remove()
        # session = db.create_scoped_session()
        # camera = session.merge(camera)
        # processors = [session.merge(p) for p in processors]
        # db.session = session
        # logging.info('Session refreshed')
        # close session for connections to be reset properly
        # db.session.close()
        # load stream info until it is done
        try:
            playlist = m3u8.load(camera.stream_url)
            stream_info = playlist.playlists[0].stream_info
            stream = m3u8.load(playlist.playlists[0].absolute_uri)
            logging.info('Stream frame rate is: {}'.format(stream_info.frame_rate))
        except URLError:
            logging.warning('Failed to connect with camera {}'.format(camera.id))
            logging.warning('Sleeping for {} seconds'.format(reconnect_time))
            time.sleep(reconnect_time)
            continue

        # process segments
        n_segments = len(stream.segments)
        for segment in stream.segments:
            if segment.absolute_uri not in last_processed_segments:
                t01 = time.time()
                segment_fp = os.path.join(camera_tmp_dir, segment.uri.replace('/', '_'))
                logging.info('Download ts file: {} to {}'.format(segment.absolute_uri, segment_fp))
                segment_downloaded = False
                for attempt in range(max_attempts_to_dl_segment):
                    try:
                        resource = urlopen(segment.absolute_uri, timeout=2)
                        logging.debug('Opening file')
                        out = open(segment_fp, 'wb')
                        logging.debug('Writing to file')
                        out.write(resource.read())
                        fs = out.tell()
                        logging.debug('File size: {}'.format(fs))
                        logging.debug('Closing file')
                        out.close()
                        logging.debug('Done')
                        # By some reasons an empty file can be downloaded from web camera.
                        # HTTP response will be 200 but nothing will be downloaded.
                        # TO fix this I check file size and if it is 0 it must be downloaded again
                        if fs > 0:
                            segment_downloaded = True
                            break
                    except Exception as e:
                        logging.error('Failed to download {}'.format(segment.absolute_uri))
                        logging.error(traceback.format_exc())
                        logging.error(str(e))
                        time.sleep(1)
                if not segment_downloaded:
                    logging.error('Segment was not downloaded. Skipping.')
                    continue
                t02 = time.time()
                logging.info('Open video')
                cap = cv2.VideoCapture(segment_fp)
                t03 = time.time()
                logging.info('Select frames')
                frames = []
                frame_id = 0
                ret, img = cap.read()
                while ret:
                    if ret and frame_id % round(stream_info.frame_rate / camera.watch_fps) == 0:
                        ts = segment.current_program_date_time + dt.timedelta(
                            seconds=frame_id / stream_info.frame_rate) + dt.timedelta(hours=camera.tz)
                        logging.debug('Acceptes ts: {}'.format(ts))
                        frames.append(Frame(img, ts))
                    frame_id += 1
                    ret, img = cap.read()
                logging.info('Frames to process: {}'.format(len(frames)))
                if cap and cap.isOpened():
                    cap.release()
                t04 = time.time()
                try:
                    os.remove(segment_fp)
                except FileNotFoundError:
                    logging.warning('Failed to remove {}: it does not exist'.format(segment_fp))
                t05 = time.time()
                logging.info('Download ts: {:.2f}, Open ts: {:.2f}, Select frames: {:.2f}, '
                             'Delete ts: {:.2f}'.format(t02 - t01,
                                                        t03 - t02,
                                                        t04 - t03,
                                                        t05 - t04))
                if frames:
                    # detect objects at Frames
                    try:
                        detect_objs(frames, camera.grid_size)
                    except Exception as e:
                        logging.error('Failed to detect objects')
                        logging.error(traceback.format_exc())
                        logging.error(str(e))
                        break

                    t06 = time.time()

                    # todo: async
                    # calculate and save / send metrics
                    for proc in enabled_procs:
                        logging.debug('Started {}'.format(proc.__class__.__name__))
                        t1 = time.time()
                        proc.process(frames)
                        t2 = time.time()
                        logging.debug('Finished {} for {:.2f}'.format(proc.__class__.__name__, t2 - t1))
                    t07 = time.time()
                    logging.info('Detect objs: {:.2f}, Process frames: {:.2f}'.format(t06 - t05, t07 - t06))
                    logging.info('Total time {:.2f}'.format(t07 - t01))
                else:
                    logging.warning('No frames found')
            last_processed_segments.append(segment.absolute_uri)
        # leave only last processed segments
        last_processed_segments = last_processed_segments[-n_segments:]
        time.sleep(max(1, (n_segments - 2) * stream.target_duration))
