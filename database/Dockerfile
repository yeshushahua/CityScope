FROM postgis/postgis:16-3.4@sha256:44126d872ac91993766c341e369c539e8196614321765d36a6f1bab0419a5fa5

ARG PGROUTING_PACKAGE_VERSION=3.8.0-1.pgdg110+1

RUN apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install --yes --no-install-recommends \
       postgresql-16-pgrouting=${PGROUTING_PACKAGE_VERSION} \
       postgresql-16-pgrouting-scripts=${PGROUTING_PACKAGE_VERSION} \
    && rm -rf /var/lib/apt/lists/*
