from .base import *
import dj_database_url

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Allowed hosts
allowed_hosts_env = os.environ.get('DJANGO_ALLOWED_HOSTS')
ALLOWED_HOSTS = allowed_hosts_env.split(',') if allowed_hosts_env else []

# Tell Django to trust the 'X-Forwarded-Proto' header from the Google Cloud proxy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Set the 'Secure' flag on session and CSRF cookies
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Also add your app's domain to the trusted origins for CSRF
CSRF_TRUSTED_ORIGINS = [
    'https://hobart-app-593929177358.us-central1.run.app'
    # Add any other custom domains you might use here
]

# (Optional, but highly recommended for production)
# Redirect all HTTP requests to HTTPS
SECURE_SSL_REDIRECT = True

# Production database configuration
DATABASES = {
    'default': dj_database_url.config(
        conn_max_age=600,
        engine='django.contrib.gis.db.backends.postgis'
    )
}
