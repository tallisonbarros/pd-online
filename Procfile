web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 120 --max-requests 500 --max-requests-jitter 50 --access-logfile - --error-logfile -
