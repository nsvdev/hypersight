from flask import request, session
from flask_babelex import Babel

babel = Babel()


@babel.localeselector
def get_locale():
    """
    Selects language for current session
    :return:
    """
    if request.args.get('lang'):
        session['lang'] = request.args.get('lang')
    return session.get('lang', 'ru')
