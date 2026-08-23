#!/bin/sh
set -eu

uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!

nginx -g 'daemon off;' &
nginx_pid=$!

cleanup() {
    kill -TERM "$backend_pid" "$nginx_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
    wait "$nginx_pid" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$nginx_pid" 2>/dev/null; do
    sleep 1
done

exit 1
