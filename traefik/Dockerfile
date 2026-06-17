# https://hub.docker.com/_/odoo
FROM odoo:19.0

USER root

# Extra packages required by custom addons:
#   cryptography  — custom_ai_core field-level encryption (Fernet)
#   celery/redis  — task_bridge async dispatch from inside Odoo
#   minio         — future object-storage attachment backend
RUN pip3 install --no-cache-dir --break-system-packages \
    "celery[redis]>=5.4.0" \
    "redis>=5.2.1" \
    "minio>=7.2.0"

# Custom addons — bind-mounted at runtime (see docker-compose.yml volumes)
# Copying here ensures they are available in production images with no mount.
COPY addons/ /mnt/extra-addons/

USER odoo
