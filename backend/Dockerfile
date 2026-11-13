# Same supported Python minor for API/worker/jobs; Alpine avoids shipping the
# unused Debian mount/login/systemd/perl stack. Keep the distribution explicit.
FROM python:3.12-alpine3.24@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89 AS wheels

WORKDIR /build
COPY requirements.txt requirements.lock ./
# Native dependencies must provide musllinux wheels. http-ece is pure Python
# and only publishes an sdist; build its wheel here, outside the runtime stage.
RUN pip wheel --no-cache-dir --require-hashes --wheel-dir /wheels \
    --only-binary=:all: --no-binary=http-ece -r requirements.lock -r requirements.txt

FROM python:3.12-alpine3.24@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89

ARG APP_RELEASE=local
ENV APP_RELEASE=${APP_RELEASE}
LABEL org.opencontainers.image.revision=${APP_RELEASE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv

RUN apk upgrade --no-cache \
    && apk add --no-cache ca-certificates

COPY requirements.txt requirements.lock ./
# The source archives/wheels were hash-checked in the builder. Install only
# these local wheels (http-ece's built wheel has a different hash to its sdist).
RUN --mount=type=bind,from=wheels,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index /wheels/*.whl \
    && pip check

# HomeWallet uses MySQL, not SQLite. Alpine's SQLite can lag upstream fixes
# even when its vulnerability feed reports no findings. Remove the unused
# Python binding as well as the actual library. Preserve the official base's
# declared shared-library dependencies except SQLite; keep apk's inventory
# consistent without adding optional desktop/Tk libraries or build utilities.
RUN set -eu; \
    runtime_deps="$(apk info --no-network -R .python-rundeps \
        | sed -n '/^so:/p' | grep -v '^so:libsqlite3\.so\.0$')"; \
    [ -n "$runtime_deps" ]; \
    rm -f /usr/local/lib/python3.12/lib-dynload/_sqlite3*.so; \
    rm -rf /usr/local/lib/python3.12/sqlite3; \
    apk add --no-cache --virtual .homewallet-rundeps $runtime_deps; \
    apk del --no-network .python-rundeps; \
    if apk info --no-network -e sqlite-libs; then exit 1; fi

ADD --chmod=644 https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem /etc/ssl/rds-global-bundle.pem

COPY app ./app
COPY jobs ./jobs
COPY db ./db

RUN addgroup -S -g 10001 appuser \
    && adduser -S -D -u 10001 -G appuser appuser
USER 10001:10001

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "2", "--access-logfile", "-", "app.main:app"]
