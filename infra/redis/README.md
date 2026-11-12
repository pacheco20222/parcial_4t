# Redis

Compose runs `start.sh` as non-root, reads hex `/run/secrets/redis_password`,
and writes a private config into tmpfs. Password never enters argv. Protected
mode, AOF persistence, disabled FLUSHALL/FLUSHDB/CONFIG/KEYS. Port 6379 internal;
no HTTP endpoints. Services own stream/pubsub event payloads (contracts §6).

Run: `docker compose up -d redis` after bootstrap. Check: `sh -n infra/redis/start.sh`
and `python3 -m unittest discover -s scripts/tests -p test_infra.py -v`.
Live authentication, AOF and disabled-command checks need Docker.
