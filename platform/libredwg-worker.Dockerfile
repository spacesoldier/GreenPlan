FROM debian:bookworm AS build

ARG LIBREDWG_VERSION=0.14
ARG LIBREDWG_SHA256=cb6ee0b078c6d9e0f09d66f1feac33ba6342df88ae544e9f9335fab475218351
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential autoconf automake libtool pkg-config libxml2-dev libpcre2-dev texinfo \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY vendor/libredwg/packages/libredwg-0.14.tar.gz /build/libredwg-0.14.tar.gz
RUN echo "${LIBREDWG_SHA256}  libredwg-${LIBREDWG_VERSION}.tar.gz" | sha256sum -c - \
    && tar -xzf "libredwg-${LIBREDWG_VERSION}.tar.gz" \
    && cd "libredwg-${LIBREDWG_VERSION}" && ./configure --disable-write && make -j2 && make install

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip libxml2 libpcre2-8-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/dwgread /usr/local/bin/dwgread
COPY --from=build /usr/local/bin/dwg2dxf /usr/local/bin/dwg2dxf
COPY --from=build /usr/local/lib/libredwg.so* /usr/local/lib/
RUN ldconfig
COPY platform/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt
COPY platform/app /app
WORKDIR /app
