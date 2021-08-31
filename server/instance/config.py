# Flask
DEBUG = True
SECRET_KEY = r''
LOG_DIR = 'logs'
LOG_LEVEL = 10

# Admin
FLASK_ADMIN_SWATCH = 'cerulean'

# SQLAlchemy
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = True
SQLALCHEMY_ENGINE_OPTIONS = {'pool_recycle': 3600, 'pool_pre_ping': True}  # for mysql

# Celery
CELERY_RESULT_BACKEND = 'redis://localhost'
CELERY_BROKER_URL = 'redis://localhost'

# hypersight
SEGMENTS_DIR = '/tmp/hypersight/segments'  # dir for storing downloaded m3u8 segments
PROCESSORS_PREVIEW_DIR = '/tmp/hypersight/preview'  # dir for storing processed m3u8 segments
FRAMES_PATH = '/tmp/hypersight/frames'  # preview frames dir (for drawing zones)
OBJECT_DETECTOR_URL = 'http://127.0.0.1:5007/detectObjects'  # URL for object detector
FACE_DETECTOR_URL = 'http://127.0.0.1:5007/detectFaces'  # URL for face detector
FACE_WS_ADDRESS = '0.0.0.0'
FACE_WS_PORT = 6789
