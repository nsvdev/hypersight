# hypersight
This package contains Web Server responsible for video analysis.

Main features are:
- traffic counting: counts number off persons passed to some specified zone at a given time interval
- persons counting: counts number of persons in RoI at given time
- face detection: detects all faces at given ROI and time, 
notify all WS clients about found faces for further processing

## Architecture
This system works with online streams. A separate process is started and maintained by Celery for each Camera.
Inside a process there is an infinite loop for reading *ts* frames from stream and their processing.
**Object detection is made via API call to another server so no GPU is required to launch this instance.**
After processing of each segment found events are saved to the DB. 

Only events, neither metrics nor detected objects are saved to the DB. 
It allows to calculate metrics rapidly on each API call and to keep DB small enough.

The following ORM model (`models.py`) is used to access the DB:
- **Camera** holds info on connection to the stream and processing parameters (FPS, detection grid).
- **Processor** is a base class for all counters. 
These classes contain calculation parameters like RoIs, threshold as well as calculation method (*.process*).
So when some event is found (face found at RoIs or object left the scene via RoE) it saves **ProcessorEvent** to the DB.
- **ProcessorEvent** stores info on some found event: person entered some RoE, face found at some RoE etc

### Quick Start
Запустите докер и введите команду:
```
  docker-compose up --build
```

### Modules
The solution is based on three modules:
- Flask: web page rendering, DB initialization and general administration.
- Celery: spawn of watching processes (watchers)
- WebSocket: broadcasting of found faces

### Data flows
1. Watcher downloads ts segment from camera.stream_url to the `SEGMENTS_DIR` (and deletes later)
2. Watcher takes frames from this segment with camera.watch_fps rate, glues them in a mosaic and 
passes them to `OBJECT_DETECTOR_URL`
3. Watcher checks DB `SQLALCHEMY_DATABASE_URI` for active processors and passes frames with detected objects to each of them
4. Processor analyzes received frames and saves some Events to the DB
5. Processor saves output HLS if required to the `PROCESSORS_PREVIEW_DIR` with ffmpeg
6. On API call Flask reads DB `SQLALCHEMY_DATABASE_URI` and returns metrics calculated on ProcessorEvents 

## Requirements
The repo was built and tested on:
- Python 3.7
- Ubuntu 18.04
- MySQL, SQLite

It requires following additional dependencies:
- ffmpeg 3.4.6 (for output hls streaming)
- Redis server 4.0.9 (for celery)
- SQL database

## Configuration
All configuration is stored in `server/instance/config.py` for simplicity. 
There is an example config file stored in that folder.

You can `cp server/instance/config_example.py to server/instance/config.py` and 
make the following changes inside:
- SECRET_KEY for cookie crypto sign must be some random string
- setup all other parameters based on your config

## Deployment
0. Copy git repo
1. Fill config.py
2. Make venv and activate it
3. `cd project_dir`
4. `pip install requirements.txt -r`
5. Init DB:
    - `export FLASK_APP=server`
    - `flask init-db` (it will create all required schemas in a specified table and delete all existing!!)
6. Add `celery`, `restart_watchers.py` and `server` to auto start (see examples below)
7. Reboot to make sure everything is OK

### Celery daemon
Create Celery config `/etc/celery`:
```
# Name of nodes to start
# here we have a single node
CELERYD_NODES="w1"
# or we could have three nodes:
#CELERYD_NODES="w1 w2 w3"

# Absolute or relative path to the 'celery' command:
CELERY_BIN="venv/bin/celery"
#CELERY_BIN="/virtualenvs/def/bin/celery"

# App instance to use
# comment out this line if you don't use an app
CELERY_APP="celery_worker.celery"
# or fully qualified:
#CELERY_APP="proj.tasks:app"

# How to call manage.py
CELERYD_MULTI="multi"

# Extra command-line arguments to the worker
CELERYD_OPTS="--autoscale=10000,1"

# - %n will be replaced with the first part of the nodename.
# - %I will be replaced with the current child process index
#   and is important when using the prefork pool to avoid race conditions.
CELERYD_PID_FILE="/var/run/celery_%n.pid"
CELERYD_LOG_FILE="/var/log/celery/%n%I.log"
CELERYD_LOG_LEVEL="INFO"

# you may wish to add these options for Celery Beat
CELERYBEAT_PID_FILE="/var/run/celery_beat.pid"
CELERYBEAT_LOG_FILE="/var/log/celery/beat.log"



```
Create file `/etc/systemd/system/celery.service` with:
```
[Unit]
Description=Celery Service
After=network.target

[Service]
Type=forking
User=root
Group=root
EnvironmentFile=/etc/celery
WorkingDirectory=proj_dir
ExecStart=/bin/sh -c '${CELERY_BIN} multi start ${CELERYD_NODES} \
  -A ${CELERY_APP} --pidfile=${CELERYD_PID_FILE} \
  --logfile=${CELERYD_LOG_FILE} --loglevel=${CELERYD_LOG_LEVEL} ${CELERYD_OPTS}'
ExecStop=/bin/sh -c '${CELERY_BIN} multi stopwait ${CELERYD_NODES} \
  --pidfile=${CELERYD_PID_FILE}'
ExecReload=/bin/sh -c '${CELERY_BIN} multi restart ${CELERYD_NODES} \
  -A ${CELERY_APP} --pidfile=${CELERYD_PID_FILE} \
  --logfile=${CELERYD_LOG_FILE} --loglevel=${CELERYD_LOG_LEVEL} ${CELERYD_OPTS}'

[Install]
WantedBy=multi-user.target


```
Reload daemons `systemctl daemon-reload`

Start the service `systemctl start celery`

Allow to start it at system boot `systemctl enable celery`

### Flask daemon
It is much better to daemon Flask via Nginx and Gunicorn but 
for one client response process this method work good as well

Create Flask start shell script `some_path/start_flask.sh`:
```
#! /bin/bash

cd /var/www/hypersight
source venv/bin/activate
export FLASK_APP=server
export FLASK_ENV=development
export FLASK_DEBUG=0
flask run --host=0.0.0.0 # 0.0.0.0 will allow to connect from any subnet

``` 

Make it executable `chmod +x some_path/start_flask.sh`

Create file `/etc/systemd/system/flask.service` with:
```
[Unit]
Description=hypersight Flask daemon
After=network.target

[Service]
ExecStart=some_path/start_flask.sh
StandardOutput=null
StandardError=null

[Install]
WantedBy=multi-user.target
```
Reload daemons `systemctl daemon-reload`

Start the service `systemctl start flask`

Allow to start it at system boot `systemctl enable flask`


###Watchers restart
After a reboot camera watchers must be restarted.


Create Flask start shell script `some_path/restart_watchers.sh`:
```
#! /bin/bash

cd proj_path
source venv/bin/activate
python restart_watchers.py
``` 

Make it executable `chmod +x some_path/restart_watchers.sh`

Create file `/etc/systemd/system/watchers.service` with:
```
[Unit]
Description=Camera wathcers autostarter
After=network.target

[Service]
ExecStart=some_path/restart_watchers.sh

[Install]
WantedBy=multi-user.target
```
Reload daemons `systemctl daemon-reload`

Start the service `systemctl start watchers`

Allow to start it at system boot `systemctl enable watchers`

##Quick start
After successful deployment one can start processing of video streams:
0. Go to **/admin**
1. Create a **Camera**.
2. Create a required **Processor** for this Camera. If it is online the preview shot for zones will be available.
Otherwise zones must be added manually in a string mode. 
It is rather painful so it is much better to setup camera online first.
4. Don't forget to mark Processor as enabled
5. Wait for some time to get results on API or to see output stream on Processor edit tab

## API

### Metrics
All metrics can be received by a corresponding API call:

#### Traffic
Returns number of persons passed to all of ROEs detected by a Processor 
with `id=proc_id` from `start_ts` to `stop_ts` or current time.
```http request
POST /traffic
Content-Type: application/json

{
  "proc_id": 4,
  "start_ts": "2020-03-27 00:00:00.0",
  "stop_ts": "2020-03-26 00:00:00.0"
}
```
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `proc_id` | `int` | **Required**. Processor id |
| `start_ts` | `string` | **Required**. Beginning of the interval |
| `stop_ts` | `string` | End of the interval. If not specified current ts is taken as stop_ts |

Response
```json
{
  "err": false,
  "max_ts": "2020-03-27 22:34:16.068667",
  "min_ts": "2020-03-27 14:21:01.133333",
  "traffic": 2618
}
```
Error response
```json
{
  "err": true,
  "msg": "No records found"
}
```


#### Persons
Returns number of persons at frame detected by a Processor 
with `id=proc_id` at `ts` or current time
```http request
POST /objects
Content-Type: application/json

{
  "proc_id": 4,
  "ts": "2020-03-27 00:00:00.0"
}
```
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `proc_id` | `int` | **Required**. Processor id |
| `ts` | `string` | Time for detection. If not specified current ts is taken as stop_ts |

Response
```json
{
  "err": false,
  "count": 10,
  "ts": "2020-03-26 21:54:29.006000"
}
```
Error response
```json
{
  "err": true,
  "msg": "Wrong processor id"
}
```
#### Status
Returns status of watchers for all cameras in DB
```http request
GET /statusWatch
```
Response:
```json
{
    "1": {"watching": false, "url": "http://..."}, 
    "2": {"watching": true, "url": "http://..."}, 
    "3": {"watching": false, "url": "http://..."}
}
```
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `key` | `int` | Camera id |
| `watching` | `bool` | True if there is a running process for this camera; False otherwise |
| `url` | `str` | Camera stream URL |

#### Faces
To get found faces one has to connect via WS. 
Faces are being broadcast in realtime, no saving or caching is implemented.
To start receiving faces one has to send the greeting string `client` to the `FACE_WS_ADDRESS: FACE_WS_PORT`:
After successful connection server will send `OK` and then start sending jsons with faces.
One message corresponds to some frame so multiple faces can be send in one message.

```json
{
    "frame_ts": "%Y-%m-%d %H:%M:%S.%f",
    "container": "jpg",
    "camera_id": "camera_id",
    "camera_url": "stream_url",
    "faces": [
                {
                "bbox": ["xmin", "ymin", "xmax", "ymax"], 
                "conf": "float", 
                "img": "Base64Str"
                }
             ]
}
```