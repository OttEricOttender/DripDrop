# Use the official PostGIS image — version pinned for reproducibility
FROM postgis/postgis:17-3.4

RUN apt-get update && \
    apt-get install -y postgis curl unzip \
    && apt-get purge -y --auto-remove curl unzip \
    && rm -rf /var/lib/apt/lists/*

COPY initscripts/ /docker-entrypoint-initdb.d/

