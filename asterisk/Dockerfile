FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    asterisk \
    ffmpeg \
    python3 \
    python3-pip \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Pre-create the ASTdb SQLite database with correct schema
RUN mkdir -p /var/lib/asterisk && \
    sqlite3 /var/lib/asterisk/astdb.sqlite3 \
    "CREATE TABLE IF NOT EXISTS astdb (key VARCHAR(256), value VARCHAR(256), PRIMARY KEY(key));" && \
    chmod 755 /var/lib/asterisk && \
    chmod 644 /var/lib/asterisk/astdb.sqlite3

RUN pip3 install requests

# Copy Asterisk config files
COPY etc/ /etc/asterisk/

# Copy AGI scripts
COPY agi-bin/ /var/lib/asterisk/agi-bin/
RUN chmod +x /var/lib/asterisk/agi-bin/*.py

# Create directories Asterisk needs
RUN mkdir -p /var/spool/asterisk/outgoing \
             /var/spool/asterisk/tmp \
             /var/log/asterisk \
             /var/run/asterisk \
             /tmp/wakeup

EXPOSE 5060/udp 5060/tcp

CMD ["asterisk", "-f", "-vvv"]
