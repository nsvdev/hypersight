from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

import os

engine = create_engine('mysql://{}:{}@{}/{}'.format(
    os.getenv('DB_USER', 'flask'),
    os.getenv('DB_PASSWORD', ''),
    os.getenv('DB_HOST', 'mysql'),
    os.getenv('DB_NAME', 'flask')
))
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()


def init_db():
    """
    Removes all data in existing DB and creates a new empty one
    :return:
    """
    # noinspection PyUnresolvedReferences
    from server import models
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
