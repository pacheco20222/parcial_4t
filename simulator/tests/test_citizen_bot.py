import json
import random
import threading
from collections import Counter
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from flood_simulator import citizen_bot as bot

POINTS = [{"id": "P01", "status": "Alert"}, {"id": "P02", "status": "Watch"},
          {"id": "P03", "status": "Normal"}]


def test_selection_weighted_with_ten_percent_normal():
    rng = random.Random(42)
    counts = Counter(bot.select_point(POINTS, rng)["status"] for _ in range(10000))
    assert 850 < counts["Normal"] < 1150
    assert counts["Alert"] > counts["Watch"] * 2
    assert bot.select_point([], rng) is None
    assert bot.select_point([{"id": "P01", "status": "NoData"}], rng) is None
    # Only Normal points (dry weather): rare ambiguous reports (~15%), otherwise skip.
    dry = [bot.select_point([POINTS[2]], rng) for _ in range(10000)]
    assert 1200 < sum(p == POINTS[2] for p in dry) < 1800
    assert all(p in (None, POINTS[2]) for p in dry)


def test_templates_match_severity_and_are_bounded():
    rng = random.Random(7)
    descriptions = set()
    for point in POINTS:
        for _ in range(100):
            report = bot.build_report(point, rng)
            assert report["pointId"] == point["id"]
            assert 1 <= len(report["description"]) <= 500
            assert report["category"] in bot.TEMPLATES[point["status"]]
            descriptions.add(report["description"])
    assert len(descriptions) >= 12


def test_occasional_duplicate_when_point_still_has_same_status():
    rng = random.Random(9)
    previous = bot.build_report(POINTS[0], rng)
    reports = [bot.next_report([POINTS[0]], rng, previous) for _ in range(1000)]
    assert sum(report == previous for report in reports) > 30
    assert bot.next_report([{"id": "P01", "status": "Normal"}], rng, previous)["category"] in bot.TEMPLATES["Normal"]


@pytest.mark.parametrize("value", ["0", "149", "nan", "inf", "bad"])
def test_unsafe_interval_rejected(monkeypatch, value):
    monkeypatch.setenv("CITIZEN_BOT_MIN_INTERVAL_SECONDS", value)
    with pytest.raises(ValueError):
        bot.Config.load()


def test_config_defaults_and_disabled(monkeypatch):
    monkeypatch.delenv("CITIZEN_BOT_MIN_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("CITIZEN_BOT_ENABLED", raising=False)
    assert bot.Config.load() == bot.Config(True, 150)
    monkeypatch.setenv("CITIZEN_BOT_ENABLED", "false")
    assert not bot.Config.load().enabled


def test_http_request_has_csrf_and_timeout():
    with patch.object(bot, "urlopen") as opener:
        opener.return_value.__enter__.return_value.read.return_value = b'{}'
        bot.request_json(bot.REPORTS_URL, {"pointId": "P01"})
        request = opener.call_args.args[0]
        assert request.full_url == bot.REPORTS_URL
        assert request.get_header("X-requested-with") == "XMLHttpRequest"
        assert json.loads(request.data) == {"pointId": "P01"}
        assert opener.call_args.kwargs["timeout"] == 10


def test_get_retries_bounded():
    stop = threading.Event()
    with patch.object(bot, "request_json", side_effect=OSError), patch.object(stop, "wait", return_value=False) as wait, pytest.raises(OSError):
        bot.fetch_points(stop)
    assert wait.call_count == 2


def test_loop_429_backs_off_without_retrying_post(capsys):
    stop = threading.Event()
    def wait(delay):
        assert delay >= 600
        stop.set()
        return True
    with patch.object(bot, "fetch_points", return_value=POINTS), patch.object(bot, "request_json", side_effect=HTTPError(bot.REPORTS_URL, 429, "rate", {}, None)) as post, patch.object(stop, "wait", side_effect=wait):
        bot.run(bot.Config(), stop, random.Random(1))
    assert post.call_count == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "rate_limited"


def test_success_logs_no_body_and_waits_minimum(capsys):
    stop = threading.Event()
    def wait(delay):
        assert 150 <= delay <= 180
        stop.set()
        return True
    with patch.object(bot, "fetch_points", return_value=POINTS), patch.object(bot, "request_json", return_value={}), patch.object(stop, "wait", side_effect=wait):
        bot.run(bot.Config(), stop, random.Random(1))
    record = json.loads(capsys.readouterr().out)
    assert record["event"] == "citizen_bot.report_sent"
    assert record["service"] == "citizen-bot"
    assert "description" not in record


def test_disabled_makes_no_http_calls():
    stop = threading.Event()
    with patch.object(bot, "request_json") as request, patch.object(stop, "wait", side_effect=lambda _: stop.set()):
        bot.run(bot.Config(False), stop, random.Random(1))
    request.assert_not_called()


def test_invalid_points_are_filtered_and_no_data_skipped():
    payload = [None, {"id": 5, "status": "Alert"}, {"id": "P01", "status": {}},
               {"id": "P02", "status": "NoData"}, POINTS[0]]
    with patch.object(bot, "request_json", return_value=payload):
        points = bot.fetch_points(threading.Event())
    assert bot.select_point(points, random.Random(2)) == POINTS[0]


def test_get_can_recover_and_sigterm_interrupts_backoff():
    stop = threading.Event()
    with patch.object(bot, "request_json", side_effect=[OSError(), POINTS]) as request, patch.object(stop, "wait", return_value=False):
        assert bot.fetch_points(stop) == POINTS
        assert request.call_count == 2
    with patch.object(bot, "request_json", side_effect=OSError) as request, patch.object(stop, "wait", return_value=True):
        assert bot.fetch_points(stop) == []
        assert request.call_count == 1


def test_failed_post_waits_without_immediate_retry(capsys):
    stop = threading.Event()
    with patch.object(bot, "fetch_points", return_value=POINTS), patch.object(bot, "request_json", side_effect=TimeoutError) as request, patch.object(stop, "wait", side_effect=lambda _: stop.set()):
        bot.run(bot.Config(), stop, random.Random(1))
    assert request.call_count == 1
    assert json.loads(capsys.readouterr().out)["event"] == "citizen_bot.error"


def test_previous_description_cannot_outlive_severity():
    # Drainage category exists in both severities, but descriptions must still match.
    previous = {"pointId": "P01", "category": "DrenajeTapado",
                "description": bot.TEMPLATES["Watch"]["DrenajeTapado"][0]}
    point = {"id": "P01", "status": "Normal"}
    for seed in range(100):
        assert bot.next_report([point], random.Random(seed), previous) != previous


def test_main_handles_sigterm_and_invalid_config(monkeypatch):
    handlers = {}
    monkeypatch.setattr(bot.signal, "signal", lambda sig, handler: handlers.update({sig: handler}))
    def run(config, stop, rng):
        handlers[bot.signal.SIGTERM](bot.signal.SIGTERM, None)
        assert stop.is_set()
    with patch.object(bot, "run", side_effect=run):
        assert bot.main() == 0
    monkeypatch.setenv("CITIZEN_BOT_ENABLED", "invalid")
    assert bot.main() == 1


@pytest.mark.parametrize("retry_after,expected", [("900", 900), ("999999", 3600), ("bad", 600)])
def test_429_retry_after_is_bounded(retry_after, expected):
    stop = threading.Event()
    def wait(delay):
        assert delay == expected
        stop.set()
    error = HTTPError(bot.REPORTS_URL, 429, "rate", {"Retry-After": retry_after}, None)
    with patch.object(bot, "fetch_points", return_value=POINTS), patch.object(bot, "request_json", side_effect=error), patch.object(stop, "wait", side_effect=wait):
        bot.run(bot.Config(), stop, random.Random(1))
