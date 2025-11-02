# In core/management/commands/upload_data.py

import os
import re
import shlex
import subprocess
import sys
import time
from contextlib import contextmanager

import psycopg2
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from google.cloud import secretmanager

# --- Configuration (from your project files) ---
PROJECT_ID = "hobart-476116"
INSTANCE_CONNECTION_NAME = "hobart-476116:us-central1:hobart-postgres-db"
DB_SECRET_NAME = "database_url"
PROXY_PORT = 5433  # Port to run the proxy on
FIXTURE_FILE = "hobart_data.json"

# Apps to dump
DJANGO_APPS_TO_DUMP = [
    "users", "employees", "address", "client", "organization", "core"
]


# -----------------------------------------------


@contextmanager
def cloud_sql_proxy(proxy_pid):
    """Context manager to start and automatically stop the proxy."""
    try:
        yield
    finally:
        print("---")
        print(f"✅ Shutting down Cloud SQL Proxy (PID {proxy_pid})...")
        try:
            proxy_pid.terminate()
            proxy_pid.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proxy_pid.kill()
        print("Proxy shut down.")


class Command(BaseCommand):
    help = 'Dumps local data and uploads it to the production Cloud SQL database.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("---"))
        self.stdout.write(self.style.SUCCESS(f"✅ Step 1: Dumping local data to {FIXTURE_FILE}..."))

        with open(FIXTURE_FILE, 'w') as f:
            call_command(
                'dumpdata',
                *DJANGO_APPS_TO_DUMP,
                exclude=['contenttypes', 'auth.permission'],
                format='json',
                stdout=f
            )
        self.stdout.write("Dump complete.")

        self.stdout.write(self.style.SUCCESS("---"))
        self.stdout.write(self.style.SUCCESS("✅ Step 2: Fetching production DB secret..."))

        prod_db_url = self.fetch_secret()
        self.stdout.write("Secret fetched.")

        self.stdout.write(self.style.SUCCESS("---"))
        self.stdout.write(self.style.SUCCESS(f"✅ Step 3: Starting Cloud SQL Proxy on port {PROXY_PORT}..."))

        proxy_command = f"cloud-sql-proxy {INSTANCE_CONNECTION_NAME} --port={PROXY_PORT}"
        proxy_process = subprocess.Popen(shlex.split(proxy_command), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        # Give it a moment to start
        time.sleep(3)

        # Check if it failed to start
        if proxy_process.poll() is not None:
            _, stderr = proxy_process.communicate()
            self.stderr.write(self.style.ERROR(f"🚨 ERROR: Cloud SQL Proxy failed to start:\n{stderr.decode()}"))
            return

        self.stdout.write(f"Proxy started with PID {proxy_process.pid}.")

        # Use context manager to ensure proxy is killed
        with cloud_sql_proxy(proxy_process):
            self.stdout.write(self.style.SUCCESS("---"))
            self.stdout.write(self.style.SUCCESS("✅ Step 4: Building proxy connection URL..."))

            proxy_db_url = self.build_proxy_url(prod_db_url)
            if not proxy_db_url:
                return

            self.stdout.write("Proxy URL ready.")

            self.stdout.write(self.style.SUCCESS("---"))
            self.stdout.write(self.style.SUCCESS("✅ Step 5: Enabling PostGIS on production DB..."))

            if not self.enable_postgis(proxy_db_url):
                return

            self.stdout.write("PostGIS check complete.")

            self.stdout.write(self.style.SUCCESS("---"))
            self.stdout.write(self.style.SUCCESS(f"✅ Step 6: Loading {FIXTURE_FILE} into production..."))
            self.stdout.write("(This may take a while. Grab a coffee ☕)")

            # Set the DATABASE_URL for the loaddata command
            os.environ['DATABASE_URL'] = proxy_db_url

            try:
                # We *must* use the production settings to load the data
                call_command('loaddata', FIXTURE_FILE, settings="Hobart.settings.production")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"🚨 ERROR during loaddata: {e}"))
                return
            finally:
                # Clean up the environment variable
                del os.environ['DATABASE_URL']

        self.stdout.write(self.style.SUCCESS("---"))
        self.stdout.write(self.style.SUCCESS("🎉 SUCCESS: Data load complete."))

    def fetch_secret(self):
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{PROJECT_ID}/secrets/{DB_SECRET_NAME}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"🚨 ERROR fetching secret: {e}"))
            self.stderr.write(
                "Is gcloud authenticated? Try `gcloud auth login` and `gcloud config set project {PROJECT_ID}`.")
            sys.exit(1)

    def build_proxy_url(self, prod_db_url):
        # Extracts 'USER:PASS' from 'postgres://USER:PASS@/DBNAME?host...'
        match_user_pass = re.search(r'postgres://(.*?@)', prod_db_url)
        # Extracts 'DBNAME' from 'postgres://USER:PASS@/DBNAME?host...'
        match_db_name = re.search(r'@/(.*?)\?host=', prod_db_url)

        if not match_user_pass or not match_db_name:
            self.stderr.write(self.style.ERROR(
                "🚨 ERROR: Could not parse DB URL secret. Is it in the format 'postgres://USER:PASS@/DBNAME?host=...'?"))
            return None

        user_pass = match_user_pass.group(1)
        db_name = match_db_name.group(1)

        return f"postgres://{user_pass}localhost:{PROXY_PORT}/{db_name}"

    def enable_postgis(self, proxy_db_url):
        try:
            conn = psycopg2.connect(proxy_db_url)
            conn.autocommit = True  # Required for CREATE EXTENSION
            with conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
            conn.close()
            return True
        except Exception as e:
            # Ignore "already exists" errors, but fail on others
            if "already exists" not in str(e):
                self.stderr.write(self.style.ERROR(f"🚨 ERROR: Failed to enable PostGIS: {e}"))
                self.stderr.write("Check your database user permissions.")
                return False
            self.stdout.write("PostGIS extension already exists, skipping.")
            return True