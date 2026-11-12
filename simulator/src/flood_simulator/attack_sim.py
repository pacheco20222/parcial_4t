"""Bounded SIEM demonstrations against the explicitly confirmed lab broker."""

import os
import secrets
import time
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv4Network
from uuid import uuid4

from .model import STATIONS, build_payload, topic
from .runtime import Config, DeviceClient, log, stop_event

ATTACK_SCENARIOS = {"all", "bruteforce", "acl_violation", "flood", "spoof", "foreign_network"}


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


def run_scenario(name: str, config: Config, stop) -> bool:
    station = STATIONS[1] if name == "acl_violation" else STATIONS[0]
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


def main() -> int:
    log("attack.banner", service="attack-sim",
        banner="LAB ONLY: SIEM attack simulation against our own mosquitto broker")
    try:
        scenario = require_lab(os.environ)
        config = Config.load()
        stop = stop_event()
        names = (
            ("bruteforce", "acl_violation", "flood", "spoof", "foreign_network")
            if scenario == "all" else (scenario,)
        )
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
    raise SystemExit(main())
