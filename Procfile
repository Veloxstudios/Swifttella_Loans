release: python manage.py migrate --noinput && python manage.py createcachetable
web: python manage.py collectstatic --noinput && gunicorn swiftella.wsgi --bind 0.0.0.0:$PORT --workers 2 --log-file -
