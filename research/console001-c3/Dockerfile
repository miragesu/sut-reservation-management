FROM debian:bookworm-slim@sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3
RUN --mount=type=secret,id=ca,target=/run/ca.pem,mode=0444 \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get -o Acquire::https::CaInfo=/run/ca.pem update && \
    apt-get -o Acquire::https::CaInfo=/run/ca.pem install -y --no-install-recommends tmux openssh-server openssh-client python3 procps && \
    rm -rf /var/lib/apt/lists/* /etc/ssh/ssh_host_*
COPY . /research
RUN chmod 755 /research && chmod 644 /research/*.py
CMD ["python3", "/research/validate.py"]
