FROM --platform=linux/arm64 debian:trixie AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_ROOT_USER_ACTION=ignore
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ENV PLATFORMIO_CORE_DIR=/build/firmware/pio/core
ENV PLATFORMIO_LIBDEPS_DIR=/build/firmware/pio/libdeps
ENV PLATFORMIO_PACKAGES_DIR=/build/firmware/pio/packages
ENV PLATFORMIO_SETTING_ENABLE_TELEMETRY=0
ENV PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL=3650

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential ca-certificates curl debhelper devscripts dh-python \
    dpkg-dev file git gzip jq lsb-release pkg-config tar \
    python3-pip python3-protobuf python3-grpcio python3-grpc-tools \
    libyaml-cpp-dev libjsoncpp-dev libgpiod-dev libbluetooth-dev \
    libusb-1.0-0-dev libi2c-dev libuv1-dev libssl-dev \
    libulfius-dev liborcania-dev libx11-dev libinput-dev \
    libxkbcommon-x11-dev libsqlite3-dev libsdl2-dev \
    libcurl4-gnutls-dev \
    && pip3 install --no-cache-dir platformio \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build/firmware
COPY . .

RUN platformio pkg install -e native-tft \
    && platformio pkg install -e native-tft -t platformio/tool-scons@4.40502.0 \
    && cp pio/core/.cache/downloads/usage.db pio/core/.cache/downloads/usage.db.bak \
    && jq -c 'with_entries(.value |= (. | tostring + "1" | tonumber))' \
       pio/core/.cache/downloads/usage.db.bak \
       > pio/core/.cache/downloads/usage.db \
    && tar -cf pio.tar pio/ \
    && rm -rf pio \
    && curl -fL "https://github.com/meshtastic/web/releases/download/v$(cat bin/web.version)/build.tar" \
       -o web.tar

ARG PKG_VERSION
ARG SOURCE_REV

RUN export DEBFULLNAME="LILYGO" DEBEMAIL="support@lilygo.cc" \
    && dch --newversion "$PKG_VERSION" \
       --distribution unstable \
       "LPM aarch64 build from commit $SOURCE_REV" \
    && dpkg-buildpackage --no-sign --build=binary --no-check-builddeps

FROM scratch AS artifact
COPY --from=builder /build/meshtasticd_*_arm64.deb /
