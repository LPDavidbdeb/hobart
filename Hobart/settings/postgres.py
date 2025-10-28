from .base import *
import dj_database_url
import os

# Check if we are running in a Google Cloud Run environment
if 'K_SERVICE' in os.environ:
    # Production settings on Cloud Run
    DEBUG = False
    ALLOWED_HOSTS = [os.environ.get('K_SERVICE') + '.run.app', '.run.app']
    
    # CSRF settings for HTTPS
    CSRF_TRUSTED_ORIGINS = ['https://' + os.environ.get('K_SERVICE') + '.run.app']
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
else:
    # Local development settings
    DEBUG = os.environ.get('DEBUG', 'True') == 'True'
    ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-postgres-development-key')

# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases
# Use dj-database-url to parse the DATABASE_URL environment variable
DATABASES = {
    'default': dj_database_url.config(default=os.environ.get('DATABASE_URL_POSTGRES'))
}
