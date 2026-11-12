FROM caddy:2.10.2-alpine
# Persistent CA/config volumes must be writable by the unprivileged gateway.
RUN mkdir -p /data /config && chown -R 1000:1000 /data /config
USER 1000:1000
