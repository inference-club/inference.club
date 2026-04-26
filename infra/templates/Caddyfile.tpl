# Caddy auto-issues Let's Encrypt certs for both hostnames once their A records
# point at this server. Until then, Caddy will retry in the background and the
# site will be unreachable over HTTPS — that's fine, DNS is the gating step.

__DOMAIN__ {
    encode zstd gzip
    reverse_proxy frontend:3000
}

api.__DOMAIN__ {
    encode zstd gzip
    # Streaming responses (SSE from /v1/chat/completions) need flush_interval to
    # disable buffering so chunks reach the client as the upstream emits them.
    reverse_proxy backend:8001 {
        flush_interval -1
    }
}
