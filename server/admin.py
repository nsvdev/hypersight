from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from wtforms.validators import number_range, regexp

from server.database import db_session
from server.models import TrafficCounter, Camera, ObjectsCounter, FaceDetector
from server.tasks import watch_camera


class CameraModelView(ModelView):
    """
    Customization of a camera view
    """
    column_labels = dict(watch_fps='FPS считывания', watch_rows='Строк в детектор', watch_cols='Колонок в детектор',
                         tz='Часовой пояс', stream_url='URL камеры')

    form_excluded_columns = ['processors']

    def after_model_change(self, form, model: Camera, is_created: bool):
        if is_created:
            watch_camera.delay(camera_id=model.id)


class ProcessorModelView(ModelView):
    """
    Customization of a Processor views
    """
    edit_template = 'processor_edit.html'
    create_template = 'processor_edit.html'

    column_labels = dict(camera='Камера', threshold='Порог обнаружения', enabled='Включен',
                         output_hls='Обработанный поток', zones_str='Зоны')
    form_columns = ('camera', 'threshold', 'enabled', 'output_hls', 'zones_str')
    form_choices = {
        'type': [
            ('traffic', 'Трафик'),
            ('face', 'Лица'),
            ('object', 'Объекты')
        ]
    }
    form_args = {'threshold': {'validators': [number_range(0, 1)]},
                 'zones_str': {
                     'validators':
                         [regexp(r'^\[(\[(\[\d\.?\d{0,}, {0,}\d\.?\d{0,}\],? {0,}){3,}\],? {0,}){0,}\]$')]}}
    form_widget_args = {
        'enabled': {
            'style': 'float:left; margin: 5px 0px; width: 0px;'
        },
        'output_hls': {
            'style': 'float:left; margin: 5px 0px; width: 0px;'
        }
    }


adm = Admin(name='hypersight', template_mode='bootstrap3')
adm.add_view(CameraModelView(Camera, db_session))
adm.add_view(ProcessorModelView(TrafficCounter, db_session))
adm.add_view(ProcessorModelView(ObjectsCounter, db_session))
adm.add_view(ProcessorModelView(FaceDetector, db_session))
