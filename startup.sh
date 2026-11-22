#!/bin/sh
# Azure App Service start-up command: apply migrations, then serve with gunicorn.
set -e
python manage.py migrate --noinput
python manage.py createcachetable
python manage.py collectstatic --noinput
mkdir -p "${MEDIA_ROOT:-/home/data/media}"
exec gunicorn config.wsgi --bind=0.0.0.0:8000 --workers=3 --timeout=60 --access-logfile=-
