import asyncio
import logging
import os
import signal
import sys
from logging.handlers import RotatingFileHandler
from logging import Logger
import websockets

from server.instance.config import LOG_DIR, FACE_WS_ADDRESS, FACE_WS_PORT


def create_rotating_log(log_dir: str, fn: str, level: int) -> Logger:
    # logging
    logger = logging.getLogger()
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)
    handler = RotatingFileHandler(os.path.join(log_dir, fn), maxBytes=10000, backupCount=5)
    # handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler(sys.stdout))
    logger.setLevel(level)
    return logger


log = create_rotating_log(LOG_DIR, 'faces_ws_server.log', logging.INFO)
clients = []
detectors = []


async def register(websocket):
    con_type = await websocket.recv()
    if con_type == 'client':
        clients.append(websocket)
    elif con_type == 'detector':
        detectors.append(websocket)
    else:
        log.warning('Unknown connection type: {}'.format(con_type))
        return
    logging.info('{} connected'.format(con_type))
    await websocket.send('OK')


async def unregister(websocket):
    if websocket in clients:
        clients.remove(websocket)
        await websocket.close()
        logging.info('client disconnected')
    if websocket in detectors:
        detectors.remove(websocket)
        await websocket.close()
        logging.info('detector disconnected')


async def echo(websocket, path):
    await register(websocket)
    try:
        logging.info('Connection')
        async for message in websocket:
            log.debug(message)
            if clients:
                await asyncio.wait([user.send(message) for user in clients])
    finally:
        await unregister(websocket)


async def echo_server(address: str, port: int, stop):
    async with websockets.serve(echo, address, port):
        await stop


if __name__ == '__main__':
    address = FACE_WS_ADDRESS
    port = FACE_WS_PORT
    log.info('*' * 20)
    log.info('Starting WS relay server at {}:{}'.format(address, port))
    loop = asyncio.get_event_loop()
    # The stop condition is set when receiving SIGTERM.
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)
    log.info('Waiting for connections')
    loop.run_until_complete(echo_server(address, port, stop))
    # loop.run_forever()
    log.info('Ended')
    logging.info('*' * 20)
