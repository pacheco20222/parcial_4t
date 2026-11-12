# Secret bootstrap and offline checks

`bash scripts/bootstrap.sh` creates the contract's secrets; reruns preserve them.
Requires OpenSSL, Python 3 and Docker for Mosquitto password hashing. Never prints
passwords. `--force` rotates files; it does not rotate existing database/accounts.
Secrets use 0644 files under a 0700 directory for explicit non-root mounts.
No env secrets, endpoints or emitted application events.

Test: `python3 -m unittest discover -s scripts/tests -v` and
`bash -n scripts/bootstrap.sh`. Tests use real OpenSSL and a Docker double.
See `infra/README.md` for full stack startup, configuration and limitations.
