FROM cloudflare/cloudflared:2024.12.2 AS cloudflared

FROM alpine:3.22.2

RUN addgroup -S cloudops \
    && adduser -S -G cloudops -H cloudops

COPY --from=cloudflared /usr/local/bin/cloudflared /usr/local/bin/cloudflared
COPY scripts/selfhost/cloudflared-entrypoint.sh /usr/local/bin/cloudops-cloudflared

RUN chmod 0555 /usr/local/bin/cloudflared /usr/local/bin/cloudops-cloudflared

USER cloudops

ENTRYPOINT ["/usr/local/bin/cloudops-cloudflared"]
