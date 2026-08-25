#!/usr/bin/env bash
# Exit immediately if any command fails
set -o errexit

echo "=== [CWMS] Starting Render Build Process ==="

# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Collect static files for WhiteNoise
python manage.py collectstatic --no-input

# 3. Run database migrations
python manage.py migrate

# 4. Auto-create superuser if credentials are provided in env vars
python manage.py shell -c "
from django.contrib.auth import get_user_model
import os

User = get_user_model()
username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

if username and password:
    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username=username, email=email or 'admin@cwms.com', password=password)
        print('SUCCESS: Superuser created -> ' + username)
    else:
        print('INFO: Superuser already exists.')
else:
    print('WARNING: Skipping superuser creation due to missing environment variables.')
"

echo "=== [CWMS] Build & Setup Completed Successfully ==="