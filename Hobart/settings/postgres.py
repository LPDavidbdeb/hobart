from .base import *
import dj_database_url
import os

# Check if we are running in a Google Cloud Run environment
# This file is for local PostgreSQL development.
# Production settings are handled by 'production.py'.
DEBUG = True
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-postgres-development-key')

# --- GeoDjango Configuration ---
# Explicitly point to the GDAL and GEOS libraries within Postgres.app
GDAL_LIBRARY_PATH = '/Applications/Postgres.app/Contents/Versions/latest/lib/libgdal.dylib'
GEOS_LIBRARY_PATH = '/Applications/Postgres.app/Contents/Versions/latest/lib/libgeos_c.dylib'

# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases
# Use dj-database-url to parse the DATABASE_URL environment variable.
# The default points to a standard local PostgreSQL setup.
DATABASES = {
    'default': dj_database_url.config(default='postgis://louis-philippedavid@localhost:5432/hobart_local')
}
