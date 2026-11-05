FROM sut-console001-c:local AS application
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN --mount=type=secret,id=build_ca,mode=0444 \
    apt-get -o Acquire::https::CaInfo=/run/secrets/build_ca update \
    && apt-get -o Acquire::https::CaInfo=/run/secrets/build_ca install -y --no-install-recommends openssh-server tmux \
    && rm -rf /var/lib/apt/lists/* /etc/ssh/ssh_host_* \
    && groupadd --gid 10001 sut && useradd --uid 10001 --gid sut --no-create-home sut \
    && groupadd --gid 10002 sut-broker && useradd --uid 10002 --gid sut-broker --groups sut --no-create-home sut-broker \
    && useradd --uid 11000 --create-home --shell /bin/bash mockconsole
# Copy the actual application's locked runtime and code. SSH tools cache independently
# of UI changes; fixtures never replace or stub the Broker/Gateway implementation.
COPY --from=application /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=application /app/ /app/
COPY tests/console_mock/ /mock/
RUN chmod -R a+rX /mock
HEALTHCHECK NONE
ENTRYPOINT ["python", "/mock/server.py"]
