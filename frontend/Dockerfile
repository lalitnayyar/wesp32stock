# Lalit Stock Application - web image: built React admin served by Caddy (HTTPS + reverse proxy).
# Build context: repository root (needs ../shared).
FROM node:22-alpine AS build
WORKDIR /src/frontend
# Optional extra root CAs for TLS-inspecting networks (deploy/extra-ca/*.crt); verification stays on.
COPY deploy/extra-ca/ /extra-ca/
RUN cat /extra-ca/*.crt > /extra-ca.pem 2>/dev/null || true
ENV NODE_EXTRA_CA_CERTS=/extra-ca.pem
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY shared /src/shared
COPY frontend /src/frontend
RUN npm run build

FROM caddy:2.8-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/frontend/dist /srv
