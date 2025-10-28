"""
WSGI config for Hobart project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Default to the postgres settings for local development
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Hobart.settings.postgres')

application = get_wsgi_application()
