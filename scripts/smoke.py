#!/usr/bin/env python3
"""End-to-end smoke test through the gateway (stdlib only).

Usage: python3 scripts/smoke.py [--base https://localhost:8443] [--lifecycle]
Requires a running stack (docker compose up) and ./secrets from scripts/bootstrap.sh.
--gate (or GATE_MODE=on) sends Basic auth (GATE_USER, default demo, + secrets/gate_password)
on every request.
--lifecycle also walks the first open work order through assign -> Closed.
"""
import argparse
import base64
import http.cookiejar
import json
import os
import pathlib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
failures = 0
GATE_AUTH = None


def gate_header():
    user = os.environ.get("GATE_USER", "demo")
    pw = (ROOT / "secrets/gate_password").read_text().strip()
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


def build_opener(base, cafile):
    ctx = ssl.create_default_context(cafile=cafile)
    if cafile is None and urllib.parse.urlparse(base).hostname in ("localhost", "127.0.0.1"):
        # Local dev only: Caddy `tls internal` CA. Pass --ca to verify instead
        # (docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt).
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )


def call(method, path, body=None, csrf=True):
    req = urllib.request.Request(BASE + path, method=method)
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    if GATE_AUTH:
        req.add_header("Authorization", GATE_AUTH)
    if csrf:
        req.add_header("X-Requested-With", "XMLHttpRequest")
    try:
        with opener.open(req, timeout=10) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return e.code, None


def check(name, ok, detail=""):
    global failures
    failures += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  {name} {detail}")


def main():
    status, _ = call("GET", "/api/telemetry/healthz")
    check("telemetry healthz", status == 200)
    status, _ = call("GET", "/api/ops/healthz")
    check("ops healthz", status == 200)
    status, _ = call("GET", "/soc/api/health")
    check("grafana (SOC) up", status == 200)
    status, points = call("GET", "/api/telemetry/public/points")
    check("public points = 5", status == 200 and len(points or []) == 5)
    check("readings ingested", bool(points) and all(p.get("updatedAt") for p in points))
    status, _ = call("GET", "/api/telemetry/kpis")
    check("kpis require auth", status == 401)
    status, _ = call("POST", "/api/ops/auth/login", {"email": "x@y.z", "password": "x"}, csrf=False)
    check("CSRF header enforced", status == 403)

    pw = (ROOT / "secrets/seed_supervisor_password").read_text().strip()
    status, body = call("POST", "/api/ops/auth/login", {"email": "supervisor@flood.local", "password": pw})
    check("supervisor login", status == 200 and body == {"mfaRequired": False})
    status, me = call("GET", "/api/ops/auth/me")
    check("auth/me", status == 200 and "Supervisor" in (me or {}).get("roles", []))
    status, kpis = call("GET", "/api/telemetry/kpis")
    check("cross-service JWT (telemetry kpis)", status == 200, json.dumps(kpis))
    status, kpis = call("GET", "/api/ops/kpis")
    check("ops kpis", status == 200, json.dumps(kpis))
    status, _ = call("GET", "/api/telemetry/points/P01/readings?bucket=5m")
    check("readings history", status == 200)
    status, rep = call("POST", "/api/ops/public/reports",
                       {"pointId": "P03", "category": "Encharcamiento", "description": "Smoke test"})
    check("citizen report", status in (200, 201) and (rep or {}).get("folio", "").startswith("RC-"))
    status, _ = call("POST", "/hubs/live/negotiate?negotiateVersion=1")
    check("SignalR negotiate", status == 200)

    if ARGS.lifecycle:
        _, orders = call("GET", "/api/ops/work-orders?status=Open")
        if not orders:
            check("lifecycle: open work order exists (run SCENARIO=storm first)", False)
            return
        order = orders[0]
        _, crews = call("GET", "/api/ops/crews")
        steps = [("assign", {"crewId": crews[0]["id"]}), ("transition", {"status": "InProgress"}),
                 ("transition", {"status": "Resolved"}), ("transition", {"status": "Closed"})]
        for ep, payload in steps:
            payload["version"] = order["version"]
            status, new = call("PATCH", f"/api/ops/work-orders/{order['id']}/{ep}", payload)
            check(f"lifecycle {ep} {payload.get('status', '')}", status == 200, f"-> {(new or {}).get('status')}")
            if status != 200:
                return
            order = new


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="https://localhost:8443")
    p.add_argument("--lifecycle", action="store_true")
    p.add_argument("--gate", action="store_true", help="send gate Basic auth (also GATE_MODE=on)")
    p.add_argument("--ca", help="CA bundle to verify the gateway certificate")
    ARGS = p.parse_args()
    if ARGS.gate or os.environ.get("GATE_MODE") == "on":
        GATE_AUTH = gate_header()
    BASE = ARGS.base.rstrip("/")
    opener = build_opener(BASE, ARGS.ca)
    main()
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
