FROM ubuntu:24.04

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 python3-pip xvfb xauth ca-certificates \
      libfontconfig1 libxcb-util1 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
      libxcb-render-util0 libxcb-shape0 libxcb-xkb1 libxkbcommon0 libxkbcommon-x11-0 \
    && rm -rf /var/lib/apt/lists/*

COPY platform/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt
COPY docker/oda-adapter/convert-dwg.sh /usr/local/bin/convert-dwg
RUN chmod 0755 /usr/local/bin/convert-dwg
COPY platform/app /app
WORKDIR /app
