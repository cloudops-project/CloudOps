#!/bin/sh
set -eu

token_path="/run/secrets/cloudflare_tunnel_token"
if [ ! -s "${token_path}" ]; then
  printf '%s\n' \
    "CONFIG_CLOUDFLARE_TOKEN_MISSING: the Cloudflare Docker secret is unavailable." >&2
  exit 2
fi

TUNNEL_TOKEN="$(cat "${token_path}")"
export TUNNEL_TOKEN

exec su-exec cloudops cloudflared --no-autoupdate tunnel run
