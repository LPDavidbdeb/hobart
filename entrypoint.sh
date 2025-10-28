#!/bin/sh

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate
# Check if migrate command was successful
if [ $? -ne 0 ]; then
  echo "Database migrations failed! Exiting."
  exit 1
fi

# Start Gunicorn server
echo "Starting Gunicorn..."
# Use exec to ensure signals are properly handled and logs are forwarded
exec gunicorn --bind :8080 --workers 2 Hobart.wsgi:application
