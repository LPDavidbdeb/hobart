#!/bin/sh

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate

# Start Gunicorn server
echo "Starting Gunicorn..."
gunicorn --bind :8080 --workers 2 Hobart.wsgi:application
