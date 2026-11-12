"""Five independent MQTT identities with elapsed-time physics."""

import random
import time
from datetime import UTC, datetime
from uuid import uuid4

from .model import (
    STATIONS,
    advance_depth,
    build_payload,
    null_depth,
    rain_intensity,
    rain_last_five_minutes,
    silent,
    topic,
)
from .runtime import Config, DeviceClient, log, stop_event


def main() -> int:
    clients = []
    try:
        config = Config.load()
        stop = stop_event()
        rng = random.Random(config.seed)
        rain_factors = [rng.uniform(0.97, 1.03) for _ in STATIONS]
        batteries = [rng.randint(90, 100) for _ in STATIONS]
        for station in STATIONS:
            client = DeviceClient(config, station.device_id)
            clients.append(client)
            client.start()
        log("simulator.started", scenario=config.scenario)
        started = time.monotonic()
        previous = 0.0
        depths = [0.0] * len(STATIONS)
        while not stop.is_set():
            tick = time.monotonic()
            elapsed = tick - started
            # Small steps preserve phase transitions even with long publish intervals.
            cursor = previous
            while cursor < elapsed:
                end = min(cursor + 1, elapsed)
                rain = rain_intensity(config.scenario, (cursor + end) / 2)
                for index, station in enumerate(STATIONS):
                    depths[index] = advance_depth(
                        depths[index], rain * rain_factors[index], end - cursor, station,
                    )
                cursor = end
            previous = elapsed
            rain5 = rain_last_five_minutes(config.scenario, elapsed)
            for index, (station, client) in enumerate(zip(STATIONS, clients, strict=True)):
                if stop.is_set():
                    break
                if silent(config.scenario, station, elapsed):
                    continue
                depth = None if null_depth(config.scenario, station, elapsed) else depths[index]
                payload = build_payload(
                    station, depth, rain5 * rain_factors[index],
                    datetime.now(UTC), uuid4(), batteries[index],
                )
                if client.publish(topic(station), payload):
                    log("simulator.published", device_id=station.device_id,
                        point_id=station.point_id)
            stop.wait(max(0.0, config.interval - (time.monotonic() - tick)))
        return 0
    except (ValueError, OSError, TypeError, KeyError):
        # Exception messages may contain secret file contents; log only a fixed message.
        log("simulator.failed", level="ERROR")
        return 1
    finally:
        for client in clients:
            client.close()
        log("simulator.stopped")
