"""
WSGI config for chat_with_mp project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/
"""

import os
from django.core.wsgi import get_wsgi_application
from wsgi_basic_auth import BasicAuth

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chat_with_mp.settings')

application = BasicAuth(get_wsgi_application())