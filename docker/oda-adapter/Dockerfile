# This image intentionally contains NO ODA binary.
# At runtime mount a locally obtained, license-accepted ODA application directory
# at /opt/oda:ro and set ODA_BIN to its ODAFileConverter executable.
FROM ubuntu:24.04

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      xvfb xauth ca-certificates libfontconfig1 \
      libxcb-util1 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
      libxcb-render-util0 libxcb-shape0 libxcb-xkb1 \
      libxkbcommon0 libxkbcommon-x11-0 \
    && rm -rf /var/lib/apt/lists/*

COPY docker/oda-adapter/convert-dwg.sh /usr/local/bin/convert-dwg
RUN chmod 0755 /usr/local/bin/convert-dwg

ENTRYPOINT ["/usr/local/bin/convert-dwg"]
