#!/usr/bin/env bash
# Exit on error
set -o errexit

python manage.py migrate

# Create a superuser if it doesn't exist
# This uses environment variables you will set in the dashboard
python manage.py shell << END
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')
    print("Superuser created.")
else:
    print("Superuser already exists.")
END

# Start the web server
gunicorn config.wsgi:application
