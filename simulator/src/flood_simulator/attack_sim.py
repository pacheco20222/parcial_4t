"""Bounded SIEM demonstrations against the explicitly confirmed lab broker."""

import argparse
import json
import math
import os
import random
import secrets
import sys
import time
from datetime import UTC, datetime
from http.client import HTTPConnection, HTTPException
from ipaddress import IPv4Address, IPv4Network
from uuid import uuid4

from .model import STATIONS, build_payload, topic
from .runtime import Config, DeviceClient, log, stop_event

SCENARIOS = (
    "bruteforce", "acl_violation", "flood", "spoof", "foreign_network",
    "login_failures", "implausible_jump",
)
ATTACK_SCENARIOS = {"all", *SCENARIOS}
# Single-message scenarios dominate; the bounded flood is deliberately rare.
SCHEDULE_WEIGHTS = (3, 6, 1, 6, 6, 3, 4)


def idmz_broker_host(environ) -> str:
    host = IPv4Address(environ.get("ATTACK_IDMZ_BROKER_HOST", "172.30.20.10"))
    network = IPv4Network("172.30.20.0/24")
    if host not in network or host in (network.network_address, network.broadcast_address):
        raise ValueError("ATTACK_IDMZ_BROKER_HOST must be a lab idmz_net host")
    return str(host)


def require_lab(environ) -> str:
    if environ.get("ATTACK_SIM_CONFIRM") != "lab":
        raise ValueError("ATTACK_SIM_CONFIRM=lab required")
    if environ.get("MQTT_HOST", "mosquitto") != "mosquitto":
        raise ValueError("only the mosquitto lab broker is allowed")
    scenario = environ.get("ATTACK_SCENARIO", "all")
    if scenario not in ATTACK_SCENARIOS:
        raise ValueError("invalid ATTACK_SCENARIO")
    if scenario in ("all", "foreign_network"):
        idmz_broker_host(environ)
    return scenario


def reading(station=STATIONS[0]) -> dict:
    return build_payload(station, 2.0, 0.0, datetime.now(UTC), uuid4())


def wait_response(client: DeviceClient, stop, timeout: float = 8) -> bool:
    deadline = time.monotonic() + timeout
    while not stop.is_set() and time.monotonic() < deadline:
        if client.responded.wait(min(0.1, max(0, deadline - time.monotonic()))):
            return True
    return False


def login_failures(stop) -> bool:
    for attempt in range(10):
        if stop.is_set():
            return False
        # Reserved invalid domain; never target a seeded account or accept an override.
        body = json.dumps({"email": "intruso@example.invalid",
                           "password": secrets.token_urlsafe(32)})
        connection = HTTPConnection("ops-service", 8080, timeout=5)
        try:
            connection.request("POST", "/auth/login", body=body, headers={
                "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest",
            })
            response = connection.getresponse()
            try:
                status = response.status
            finally:
                response.close()
        except (OSError, HTTPException):
            log("attack.connection_failed", level="ERROR", service="attack-sim",
                scenario="login_failures")
            return False
        finally:
            connection.close()
        log("attack.login_attempt", service="attack-sim", scenario="login_failures",
            attempt=attempt + 1, status=status)
        if status != 401:  # Includes 429: no immediate retry of a rate-limited request.
            return False
        if attempt < 9 and stop.wait(3):
            return False
    return True


def run_scenario(name: str, config: Config, stop) -> bool:
    if name == "login_failures":
        successful = login_failures(stop)
        log("attack.scenario_completed", service="attack-sim", scenario=name,
            status="sent" if successful else "incomplete")
        return successful
    station = STATIONS[1] if name == "acl_violation" else STATIONS[0]
    if name == "implausible_jump":
        station = STATIONS[3]
    route = {}
    if name == "foreign_network":
        station = STATIONS[2]
        route = {"connect_host": idmz_broker_host(os.environ)}
    attempts = 8 if name == "bruteforce" else 1
    successful = True
    for attempt in range(attempts):
        if stop.is_set():
            return False
        password = None
        if name == "bruteforce":
            password = secrets.token_urlsafe(32)
            # Guaranteed different from the provisioned credential, never logged.
            if password == config.passwords[station.device_id]:
                password += "-invalid"
        client = DeviceClient(config, station.device_id, password=password, reconnect=False, **route)
        try:
            client.start()
            responded = wait_response(client, stop)
            if name == "bruteforce":
                rejected = responded and not client.accepted
                successful = successful and rejected
                log("attack.login_attempt", service="attack-sim", attempt=attempt + 1,
                    device_id=station.device_id, status="rejected" if rejected else "unverified")
            elif not responded or not client.accepted:
                log("attack.connection_failed", level="ERROR", service="attack-sim")
                return False
            elif name == "acl_violation":
                for destination in (topic(STATIONS[0]), "merida/flood/P01/DEV-P01-A/command"):
                    if stop.is_set():
                        return False
                    successful = client.publish(destination, reading(station)) and successful
            elif name == "spoof":
                successful = client.publish(topic(station), reading(STATIONS[1]))
            elif name == "foreign_network":
                successful = client.publish(topic(station), reading(station))
            elif name == "implausible_jump":
                baseline = build_payload(station, 5.0, 0.0, datetime.now(UTC), uuid4())
                if not client.publish(topic(station), baseline) or stop.wait(20):
                    return False
                # Range guard also ensures suspect quality if concurrent telemetry
                # prevents the baseline becoming the last accepted reading.
                jumped = build_payload(station, 151.0, 0.0, datetime.now(UTC), uuid4())
                successful = client.publish(topic(station), jumped)
            elif name == "flood":
                started = time.monotonic()
                for index in range(30):
                    if stop.wait(max(0, started + index * (10 / 30) - time.monotonic())):
                        return False
                    successful = client.publish(
                        topic(station), reading(station), timeout=0.2,
                    ) and successful
        finally:
            client.close()
        if name == "bruteforce" and attempt < attempts - 1 and stop.wait(0.5):
            return False
    log("attack.scenario_completed", service="attack-sim", scenario=name,
        status="sent" if successful else "incomplete")
    return successful


def schedule_interval(environ) -> float:
    minutes = float(environ.get("ATTACK_INTERVAL_MINUTES", "12"))
    if not math.isfinite(minutes) or minutes < 5 or not math.isfinite(minutes * 78):
        raise ValueError("ATTACK_INTERVAL_MINUTES must be finite and at least 5")
    return minutes * 60


def run_schedule(config: Config, stop, interval: float, rng: random.Random) -> None:
    while not stop.wait(interval * rng.uniform(0.7, 1.3)):
        if stop.is_set():
            break
        name = rng.choices(SCENARIOS, weights=SCHEDULE_WEIGHTS, k=1)[0]
        log("attack.scheduled_run", service="attack-sim", scenario=name)
        try:
            if not run_scenario(name, config, stop):
                log("attack.scenario_failed", level="WARNING", service="attack-sim", scenario=name)
        except Exception:  # noqa: BLE001 -- keep demo scheduling alive after scenario failures
            # A demo failure must not kill the scheduler; never log exception secrets.
            log("attack.scenario_failed", level="ERROR", service="attack-sim", scenario=name)


def main(argv=()) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", action="store_true")
    args = parser.parse_args(argv)
    log("attack.banner", service="attack-sim",
        banner="LAB ONLY: SIEM attack simulation against our own MQTT and Ops services")
    try:
        scenario = require_lab(os.environ)
        scheduled = args.schedule or os.getenv("ATTACK_SCHEDULE") == "on"
        if scheduled:
            idmz_broker_host(os.environ)
            interval = schedule_interval(os.environ)
        config = Config.load()
        stop = stop_event()
        if scheduled:
            run_schedule(config, stop, interval, random.Random())
            return 0
        names = SCENARIOS if scenario == "all" else (scenario,)
        success = True
        for name in names:
            if stop.is_set():
                break
            success = run_scenario(name, config, stop) and success
        return 0 if success else 1
    except (ValueError, OSError, TypeError, KeyError):
        log("attack.refused_or_failed", level="ERROR", service="attack-sim")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
