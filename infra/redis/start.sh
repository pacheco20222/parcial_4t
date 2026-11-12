#!/bin/sh
set -eu
umask 077
password=$(cat /run/secrets/redis_password)
# Bootstrap generates hex; reject config metacharacters rather than interpolate.
case "$password" in ''|*[!a-fA-F0-9]*) echo 'Invalid redis_password: expected nonempty hex' >&2; exit 1;; esac
cat /usr/local/etc/redis/redis.conf > /tmp/redis.conf
printf '\nrequirepass %s\n' "$password" >> /tmp/redis.conf
unset password
exec redis-server /tmp/redis.conf
