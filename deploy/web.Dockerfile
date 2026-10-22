# The single-page app behind an unprivileged nginx (user 101, port 8080). Build the SPA first
# (cd frontend && npm ci && npm run build), then from the repository root:
# docker build -f deploy/web.Dockerfile .
# No Node in the image: the build output is static files, and dist/ carries licenses.txt. No API
# host either: Compose mounts the proxy to its API (deploy/nginx-api.conf), a cluster's ingress
# routes /api itself.
FROM nginxinc/nginx-unprivileged:alpine@sha256:b5047b9b76845eac124358373c6852377c52e4b05834a47647e955dd91cb8f1e
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/nginx-api-off.conf /etc/nginx/kka/api.conf
COPY frontend/dist /usr/share/nginx/html
EXPOSE 8080
# busybox wget with -O sends a GET, unlike --spider
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/healthz"]
