#!/bin/sh

# This script automates the process of updating the local Docker-based application.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Stopping current application containers... ---"
docker-compose -f docker-compose.local.yml down

echo "\n--- Pulling latest changes from Git... ---"
git pull

echo "\n--- Rebuilding and starting application in the background... ---"
# We use -d to run it in detached mode so the script can continue.
docker-compose -f docker-compose.local.yml up --build -d

echo "\n--- Waiting for database to be ready... ---"
# A simple sleep is often enough for local setups.
sleep 10

echo "\n--- Applying database migrations... ---"
docker-compose -f docker-compose.local.yml exec web python manage.py migrate

echo "\n\n--- Update Complete! ---"
echo "The application has been updated and is running in the background."
echo "You can view the live logs by running the following command:"
echo "docker-compose -f docker-compose.local.yml logs -f"
echo "\nAccess the application at http://localhost:8000"
