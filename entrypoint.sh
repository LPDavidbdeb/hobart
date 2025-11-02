#!/bin/sh

# Apply database migrations using production settings
echo "Applying database migrations..." >&2
python manage.py migrate --settings=Hobart.settings.production

# Check if migrate command was successful
if [ $? -ne 0 ]; then
  echo "Database migrations failed! Exiting." >&2
  exit 1
fi

# Start Gunicorn server using production settings
echo "Starting Gunicorn..." >&2

# Set the DJANGO_SETTINGS_MODULE for the Gunicorn process itself
export DJANGO_SETTINGS_MODULE=Hobart.settings.production

# Use exec to start Gunicorn. It will listen on the port provided by Cloud Run.
# Using exec is important for signal handling and proper process management.
exec gunicorn --bind :$PORT --workers 2 Hobart.wsgi:application
