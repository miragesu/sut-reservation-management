FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN --mount=type=secret,id=build_ca \
    set -eu; \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    pip install --require-hashes -r requirements.txt \
    && groupadd --gid 10001 sut \
    && useradd --uid 10001 --gid sut --no-create-home sut \
    && groupadd --gid 10002 sut-broker \
    && useradd --uid 10002 --gid sut-broker --groups sut --no-create-home sut-broker \
    && mkdir -p /app/data && chown sut:sut /app/data
COPY backend/ /app/
COPY scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod -R a+rX /app && chmod 0700 /app/data
USER 10001:10001
# Compose grants port 80 binding with a container-network-namespace sysctl; no capabilities.
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:80/health', timeout=3)"]
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
