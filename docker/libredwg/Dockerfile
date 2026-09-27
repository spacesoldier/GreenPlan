# Diagnostic reader only. LibreDWG is GPL-3.0-or-later; do not link it into a
# proprietary service without a separate license review.
FROM debian:bookworm AS build

ARG LIBREDWG_VERSION=0.14
ARG LIBREDWG_SHA256=cb6ee0b078c6d9e0f09d66f1feac33ba6342df88ae544e9f9335fab475218351

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      xz-utils build-essential autoconf automake libtool \
      pkg-config libxml2-dev libpcre2-dev texinfo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY vendor/libredwg/packages/libredwg-0.14.tar.gz /build/libredwg-0.14.tar.gz
RUN echo "${LIBREDWG_SHA256}  libredwg-${LIBREDWG_VERSION}.tar.gz" | sha256sum -c - \
    && tar -xzf "libredwg-${LIBREDWG_VERSION}.tar.gz" \
    && cd "libredwg-${LIBREDWG_VERSION}" \
    && ./configure --disable-write \
    && make -j2 \
    && make install

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libxml2 libpcre2-8-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /usr/local/bin/dwgread /usr/local/bin/dwgread
COPY --from=build /usr/local/bin/dwglayers /usr/local/bin/dwglayers
COPY --from=build /usr/local/bin/dwggrep /usr/local/bin/dwggrep
COPY --from=build /usr/local/lib/libredwg.so* /usr/local/lib/
RUN ldconfig

ENTRYPOINT ["dwgread"]
