# Stage 1: build the Angular SPA (frontend/) for production.
FROM node:24.22.2-alpine AS spa
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx ng build --configuration production

# Stage 2: gateway serving the SPA build.
FROM caddy:2.10.2-alpine
# Persistent CA/config volumes must be writable by the unprivileged gateway.
RUN mkdir -p /data /config && chown -R 1000:1000 /data /config
COPY --from=spa /app/dist/alerta-pluvial/browser /srv/www
USER 1000:1000
