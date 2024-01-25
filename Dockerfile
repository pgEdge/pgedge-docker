FROM rockylinux:9.3

ARG TARGETARCH

RUN dnf install -y epel-release dnf
RUN dnf config-manager --set-enabled crb
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
    libpq \
    libssh2 \
    tar

ARG PGEDGE_USER_ID="1020"

RUN useradd -u ${PGEDGE_USER_ID} -m pgedge -s /bin/bash && \
    mkdir -p /opt/pgedge && chown -R pgedge /opt && \
    su - pgedge -c "pip3 install --user psycopg[binary]==3.1.10" && \
    dnf remove -y python-pip

ENV PGDATA /data/pgdata
RUN mkdir -p ${PGDATA} && chown -R pgedge:pgedge ${PGDATA} && chmod 777 ${PGDATA}
VOLUME /data

USER pgedge
WORKDIR /opt

ARG PGV="16"
ARG DB_USERNAME="pgedge_init"
ARG DB_NAME="pgedge_init"
ARG INIT_PASSWORD="U2D2GY7F"

ENV DB_USERNAME=${DB_USERNAME}
ENV DB_NAME=${DB_NAME}
ENV INIT_PASSWORD=${INIT_PASSWORD}
ENV PGV=${PGV}
ENV PGDATA="/opt/pgedge/data/pg${PGV}"
ENV PATH="/opt/pgedge/pg${PGV}/bin:/opt/pgedge:${PATH}"
ENV PGCONF="${PGDATA}/postgresql.conf"
ENV PGHBA="${PGDATA}/pg_hba.conf"

RUN python3 -c "$(curl -fsSL https://pgedge-download.s3.amazonaws.com/REPO/install.py)"

RUN ./pgedge/ctl install pgedge -U ${DB_USERNAME} -d ${DB_NAME} -P ${INIT_PASSWORD} --pg ${PGV} \
    && ./pgedge/ctl um install vector \
    && pg_ctl stop

WORKDIR /opt/pgedge

ARG SHARED_BUFFERS="512MB"
ARG MAINTENANCE_WORK_MEM="128MB"
ARG EFFECTIVE_CACHE_SIZE="1024MB"
ARG LOG_DESTINATION="stderr"
ARG LOG_STATEMENT="ddl"
ARG PASSWORD_ENCRYPTION="md5"

RUN sed -i "s/^#\?password_encryption.*/password_encryption = ${PASSWORD_ENCRYPTION}/g" ${PGCONF}
RUN sed -i "s/^#\?shared_buffers.*/shared_buffers = ${SHARED_BUFFERS}/g" ${PGCONF}
RUN sed -i "s/^#\?maintenance_work_mem.*/maintenance_work_mem = ${MAINTENANCE_WORK_MEM}/g" ${PGCONF}
RUN sed -i "s/^#\?effective_cache_size.*/effective_cache_size = ${EFFECTIVE_CACHE_SIZE}/g" ${PGCONF}
RUN sed -i "s/^#\?log_destination.*/log_destination = '${LOG_DESTINATION}'/g" ${PGCONF}
RUN sed -i "s/^#\?log_statement.*/log_statement = '${LOG_STATEMENT}'/g" ${PGCONF}
RUN sed -i "s/^#\?logging_collector.*/logging_collector = 'off'/g" ${PGCONF}
RUN sed -i "s/^#\?log_connections.*/log_connections = 'off'/g" ${PGCONF}
RUN sed -i "s/^#\?log_disconnections.*/log_disconnections = 'off'/g" ${PGCONF}
RUN sed -i "s/scram-sha-256/md5/g" ${PGHBA}

RUN rm -f ~/.pgpass

RUN mkdir /home/pgedge/scripts
COPY scripts/run-database.sh /home/pgedge/scripts/
COPY scripts/init-database.py /home/pgedge/scripts/

EXPOSE 5432

CMD ["/home/pgedge/scripts/run-database.sh"]
