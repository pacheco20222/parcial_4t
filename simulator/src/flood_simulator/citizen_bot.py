"""Rate-bounded, synthetic citizen reports using only the standard library."""

import json
import math
import os
import random
import signal
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

POINTS_URL = "http://telemetry-service:8000/public/points"
REPORTS_URL = "http://ops-service:8080/public/reports"
TEMPLATES = {
    "Alert": {
        "CalleIntransitable": (
            "El agua cubre la calle junto a la esquina; los carros están dando vuelta.",
            "Frente al parque el agua está alta y ya no se puede cruzar caminando.",
            "La calle está anegada, las motos están regresando por donde vinieron.",
        ),
        "Encharcamiento": (
            "El agua sigue subiendo por la banqueta cerca de la esquina.",
            "Hay mucha agua acumulada frente al parque y casi tapa la banqueta.",
        ),
    },
    "Watch": {
        "Encharcamiento": (
            "Se está juntando agua en la esquina, todavía pasan carros despacio.",
            "Hay un charco grande junto a la banqueta frente al parque.",
            "Con la lluvia se acumuló agua al cruzar la calle, cuesta pasar a pie.",
        ),
        "DrenajeTapado": (
            "La rejilla de la esquina parece tapada con hojas y el agua no baja.",
            "El agua se queda alrededor de la coladera junto a la banqueta.",
        ),
    },
    "Normal": {
        "Otro": (
            "Parece que quedó agua junto a la esquina, aunque puede ser solo un charco pequeño.",
            "Desde aquí parece que hay agua frente al parque; no alcanzo a ver bien.",
        ),
        "DrenajeTapado": (
            "Se ven hojas sobre la rejilla de la esquina, por ahora no hay mucha agua.",
            "La coladera tiene basura encima; quizá convenga revisarla antes de que llueva.",
        ),
    },
}


@dataclass(frozen=True)
class Config:
    enabled: bool = True
    min_interval: float = 150

    @classmethod
    def load(cls) -> "Config":
        enabled = os.getenv("CITIZEN_BOT_ENABLED", "true").lower()
        interval = float(os.getenv("CITIZEN_BOT_MIN_INTERVAL_SECONDS", "150"))
        if enabled not in {"true", "false"} or not math.isfinite(interval) or interval < 150:
            raise ValueError("Invalid citizen bot configuration")
        return cls(enabled == "true", interval)


def log(event: str, *, level: str = "INFO", **context: object) -> None:
    print(json.dumps({"ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                      "level": level, "service": "citizen-bot", "event": event,
                      **context}, allow_nan=False), flush=True)


def select_point(points: list[dict], rng: random.Random) -> dict | None:
    eligible = [p for p in points if p.get("status") in TEMPLATES]
    normal = [p for p in eligible if p["status"] == "Normal"]
    severe = [p for p in eligible if p["status"] != "Normal"]
    # Dry weather: only occasional ambiguous reports; storms: mostly severe points, ~10% noise.
    if normal and (rng.random() < 0.1 if severe else rng.random() < 0.15):
        return rng.choice(normal)
    if severe:
        return rng.choices(severe, weights=[8 if p["status"] == "Alert" else 3 for p in severe])[0]
    return None


def build_report(point: dict, rng: random.Random) -> dict:
    templates = TEMPLATES[point["status"]]
    category = rng.choice(list(templates))
    return {"pointId": point["id"], "category": category,
            "description": rng.choice(templates[category])}


def next_report(points: list[dict], rng: random.Random, previous: dict | None) -> dict | None:
    point = select_point(points, rng)
    if point is None:
        return None
    # Repeat a nearby observation only when its severity/category still fits.
    if (previous and previous["pointId"] == point["id"]
            and previous["description"] in TEMPLATES[point["status"]].get(previous["category"], ())
            and rng.random() < 0.08):
        return previous.copy()
    return build_report(point, rng)


def request_json(url: str, body: dict | None = None):
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers.update({"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"})
        data = json.dumps(body).encode()
    with urlopen(Request(url, data=data, headers=headers), timeout=10) as response:
        raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("Response too large")
        return json.loads(raw)


def fetch_points(stop: threading.Event) -> list[dict]:
    for attempt in range(3):
        try:
            points = request_json(POINTS_URL)
            if not isinstance(points, list) or len(points) > 10000:
                raise ValueError("Invalid points response")
            return [p for p in points if isinstance(p, dict)
                    and isinstance(p.get("id"), str) and 0 < len(p["id"]) <= 32
                    and isinstance(p.get("status"), str)]
        except (OSError, ValueError):
            if attempt == 2:
                raise
            if stop.wait(2 ** attempt):
                return []
    return []


def run(config: Config, stop: threading.Event, rng: random.Random) -> None:
    previous = None
    while not stop.is_set():
        delay = config.min_interval + rng.uniform(0, 30)
        try:
            if not config.enabled:
                log("citizen_bot.skipped", reason="disabled")
            else:
                report = next_report(fetch_points(stop), rng, previous)
                if stop.is_set():
                    break
                if report is None:
                    log("citizen_bot.skipped", reason="no_eligible_points")
                else:
                    # Never retry a POST immediately: an unknown outcome may already count.
                    request_json(REPORTS_URL, report)
                    previous = report
                    log("citizen_bot.report_sent", point_id=report["pointId"],
                        category=report["category"])
        except HTTPError as error:
            if error.code == 429:
                delay = max(delay, 600)
                try:
                    retry_after = float(error.headers.get("Retry-After", "600"))
                    if math.isfinite(retry_after):
                        delay = max(delay, min(retry_after, 3600))
                except (TypeError, ValueError):
                    pass
                log("citizen_bot.skipped", reason="rate_limited", status=429)
            else:
                log("citizen_bot.error", level="WARNING", status=error.code)
            error.close()
        except (OSError, ValueError):
            log("citizen_bot.error", level="WARNING", reason="request_failed")
        stop.wait(delay)


def main() -> int:
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    try:
        run(Config.load(), stop, random.Random())
    except ValueError:
        log("citizen_bot.error", level="ERROR", reason="invalid_configuration")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
