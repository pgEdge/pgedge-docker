FROM rockylinux/rockylinux:9.5-ubi

ARG TARGETARCH

RUN touch /etc/hostname
RUN dnf install -y epel-release dnf
RUN dnf config-manager --set-enabled crb
RUN dnf update -y --allowerasing
RUN dnf install -y --allowerasing \
    dnsutils \
    unzip \
    iputils \
    libicu \
    sqlite \
    lbzip2 \
    jq \
    net-tools \
    python-pip \
    libssh2 \
    tar \
    libedit \
    pigz \
    which

# Create a pgedge user with a known UID for installing and running Postgres.
# pgEdge binaries will be installed within /opt/pgedge.
ARG PGEDGE_USER_ID="1020"
RUN useradd -u ${PGEDGE_USER_ID} -m pgedge -s /bin/bash && \
    mkdir -p /opt/pgedge && \
    chown -R pgedge:pgedge /opt



# The container init script requires psycopg and we need ydiff to support ACE's
# CSV output.
# TODO: the CLI installation includes ydiff, but it does not include the ydiff
# executable. Installing it ourselves via pip is a workaround. It's important
# that we install the exact same version of ydiff as what's specified in the
# CLI's requirements.txt.
RUN su - pgedge -c "pip3 install --user psycopg[binary]==3.2.3 ydiff==1.3"

# Create the suggested data directory for Postgres in advance. Because Postgres
# is picky about data directory ownership and permissions, the PGDATA directory
# should be nested one level down in the volume. So our suggestion is to mount
# a volume at /data and then PGDATA will be /data/pgdata. Don't set PGDATA yet
# though since that messes with the pgEdge install.
ARG DATA_DIR="/data/pgdata"
RUN mkdir -p ${DATA_DIR} \
    && chown -R pgedge:pgedge /data \
    && chmod 750 /data ${DATA_DIR}


# The rest of installation will be done as the pgedge user
USER pgedge
WORKDIR /opt

# Used when installing pgEdge during the docker build process only. The user,
# database, and passwords for runtime containers will be configured by the
# entrypoint script at runtime.
ARG INIT_USERNAME="pgedge_init"
ARG INIT_DATABASE="pgedge_init"
ARG INIT_PASSWORD="U2D2GY7F"

# Capture these as environment variables, to be used by the entrypoint script
ENV INIT_USERNAME=${INIT_USERNAME}
ENV INIT_DATABASE=${INIT_DATABASE}
ENV INIT_PASSWORD=${INIT_PASSWORD}

# Postgres verion to install
ARG PGV="16"
ARG PGEDGE_INSTALL_URL="https://pgedge-download.s3.amazonaws.com/REPO/install.py"
ARG SPOCK_VERSION="4.0.10"

# Install pgEdge Postgres binaries and pgvector
ENV PGV=${PGV}
ENV PGDATA="/opt/pgedge/data/pg${PGV}"
ENV LD_LIBRARY_PATH="/opt/pgedge/pg${PGV}/lib:${LD_LIBRARY_PATH}"
ENV PATH="/opt/pgedge/pg${PGV}/bin:/opt/pgedge:${PATH}"
RUN python3 -c "$(curl -fsSL ${PGEDGE_INSTALL_URL})" skipcache
RUN ./pgedge/pgedge setup -U ${INIT_USERNAME} -d ${INIT_DATABASE} -P ${INIT_PASSWORD} --pg_ver ${PGV} --spock_ver ${SPOCK_VERSION} -p 5432 \
    && ./pgedge/pgedge um install vector \
    # && ./pgedge/pgedge um install postgis \
    && pg_ctl stop -t 60 --wait;



USER pgedge

# This is still required at runtime currently, but setting it earlier causes issues with dnf
ENV LD_LIBRARY_PATH="/opt/pgedge/pg${PGV}/lib"

# Customize some Postgres configuration settings in the image. You may want to
# further customize these at runtime.
ARG SHARED_BUFFERS="512MB"
ARG MAINTENANCE_WORK_MEM="128MB"
ARG EFFECTIVE_CACHE_SIZE="1024MB"
ARG LOG_DESTINATION="stderr"
ARG LOG_STATEMENT="ddl"
ARG PASSWORD_ENCRYPTION="md5"
RUN PGEDGE_CONF="${PGDATA}/postgresql.conf"; \
    PGEDGE_HBA="${PGDATA}/pg_hba.conf"; \
    sed -i "s/^#\?password_encryption.*/password_encryption = ${PASSWORD_ENCRYPTION}/g" ${PGEDGE_CONF} \
    && sed -i "s/^#\?shared_buffers.*/shared_buffers = ${SHARED_BUFFERS}/g" ${PGEDGE_CONF} \
    && sed -i "s/^#\?maintenance_work_mem.*/maintenance_work_mem = ${MAINTENANCE_WORK_MEM}/g" ${PGEDGE_CONF} \
    && sed -i "s/^#\?effective_cache_size.*/effective_cache_size = ${EFFECTIVE_CACHE_SIZE}/g" ${PGEDGE_CONF} \
    && sed -i "s/^#\?log_destination.*/log_destination = '${LOG_DESTINATION}'/g" ${PGEDGE_CONF} \
    && sed -i "s/^#\?log_statement.*/log_statement = '${LOG_STATEMENT}'/g" ${PGEDGE_CONF} \
    && sed -i "s/^#\?logging_collector.*/logging_collector = 'off'/g" ${PGEDGE_CONF} \
    && sed -i "s/^#\?log_connections.*/log_connections = 'off'/g" ${PGEDGE_CONF} \
    && sed -i "s/^#\?log_disconnections.*/log_disconnections = 'off'/g" ${PGEDGE_CONF} \
    && sed -i "s/scram-sha-256/md5/g" ${PGEDGE_HBA}

# Now it's safe to set PGDATA to the intended runtime value
ENV PGDATA=${DATA_DIR}

# The image itself shouldn't have pgpass data in it
RUN rm -f ~/.pgpass

# Place entrypoint scripts in the pgedge user's home directory
RUN mkdir /home/pgedge/scripts
COPY scripts/run-database.sh /home/pgedge/scripts/
COPY scripts/init-database.py /home/pgedge/scripts/

EXPOSE 5432
STOPSIGNAL SIGINT

CMD ["/home/pgedge/scripts/run-database.sh"]
