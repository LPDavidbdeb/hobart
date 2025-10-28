#!/bin/sh

# --- TEMPORARY AGGRESSIVE DEBUG STEP ---
# This will run `manage.py check` and capture its output to a file,
# then print that file to stderr, and exit.
# This is to force a traceback into Cloud Run logs.

DEBUG_LOG_FILE="/tmp/django_debug_output.log"

echo "--- DEBUG: Running manage.py check ---" >&2
python manage.py check --settings=Hobart.settings.postgres > "$DEBUG_LOG_FILE" 2>&1
CHECK_EXIT_CODE=$?

if [ $CHECK_EXIT_CODE -ne 0 ]; then
  echo "--- DEBUG: manage.py check FAILED! Output below: ---" >&2
  cat "$DEBUG_LOG_FILE" >&2
  echo "--- DEBUG: manage.py check FAILED! (End of output) ---" >&2
  exit 1
else
  echo "--- DEBUG: manage.py check PASSED. Proceeding to migrations. ---" >&2
fi

# --- END TEMPORARY AGGRESSIVE DEBUG STEP ---

# Apply database migrations
echo "Applying database migrations..." >&2
python manage.py migrate >&2
# Check if migrate command was successful
if [ $? -ne 0 ]; then
  echo "Database migrations failed! Exiting." >&2
  exit 1
fi

# Start Gunicorn server
echo "Starting Gunicorn..." >&2
# Use exec to ensure signals are properly handled and logs are forwarded
exec gunicorn --bind :8080 --workers 2 Hobart.wsgi:application
