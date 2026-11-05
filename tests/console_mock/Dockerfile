FROM sut-console001-c:local
USER root
RUN --mount=type=secret,id=build_ca,mode=0444 \
    apt-get -o Acquire::https::CaInfo=/run/secrets/build_ca update \
    && apt-get -o Acquire::https::CaInfo=/run/secrets/build_ca install -y --no-install-recommends openssh-server tmux \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 11000 --create-home --shell /bin/bash mockconsole
COPY tests/console_mock/ /mock/
RUN chmod -R a+rX /mock
HEALTHCHECK NONE
ENTRYPOINT ["python", "/mock/server.py"]
