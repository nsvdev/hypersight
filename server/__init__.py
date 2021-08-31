import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Union, List

import click
from flask import Flask
from flask.cli import with_appcontext

from server.tasks import celery
from server.admin import adm
from server.babel import babel
from server.database import db_session, init_db


def create_app(test_config: Union[dict, List[tuple]] = None, celery_app: bool = False):
    """Create and configure an instance of the Flask or Celery application."""
    # initialize app with configuration from config.py
    app = Flask(__name__)
    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile(os.path.join('instance', 'config.py'))
    else:
        # load the test config if passed in
        app.config.update(test_config)

    # initialize rotating file logger
    os.makedirs(app.config['LOG_DIR'], exist_ok=True)
    handler = RotatingFileHandler(os.path.join(app.config['LOG_DIR'], 'web_server.log'), maxBytes=1024 ** 2,
                                  backupCount=10)
    handler.setLevel(app.config.get('LOG_LEVEL', 20))
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)

    # initialize Flask-SQLAlchemy and the init-db command
    app.logger.info('Init Flask-SQLAlchemy')
    app.cli.add_command(init_db_command)

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        if exception:
            db_session.rollback()
        db_session.remove()

    app.logger.info('Done')

    # initialize Flask-Admin
    app.logger.info('Init Flask-Admin')
    adm.init_app(app)
    app.logger.info('Done')

    # initialize Flask-BabelEx
    app.logger.info('Init Flask-BabelEx')
    babel.init_app(app)
    app.logger.info('Done')

    # initialize Celery
    make_celery(app, celery)

    app.logger.info('Register blueprints')
    from server.api import api_bp

    app.register_blueprint(api_bp)
    app.logger.info('Done')
    if celery_app:
        return celery
    else:
        return app


def make_celery(app, celery_app):
    """
    Initialize celery from app context
    :param app:
    :param celery_app:
    :return:
    """
    # set broker url and result backend from app config
    celery_app.conf.broker_url = app.config['CELERY_BROKER_URL']
    celery_app.conf.result_backend = app.config['CELERY_RESULT_BACKEND']
    celery_app.conf.update(app.config)

    class ContextTask(celery_app.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    # noinspection PyPropertyAccess
    celery_app.Task = ContextTask
    # run finalize to process decorated tasks
    celery_app.finalize()


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Clear existing data and create new tables."""
    init_db()
    click.echo("Initialized the database.")
