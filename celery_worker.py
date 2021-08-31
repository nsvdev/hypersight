from server import create_app

celery = create_app(celery_app=True)
