"""Wait up to 120 seconds for five seeded points through the local CI gateway."""

import json
import ssl
import time
import urllib.error
import urllib.request

URL = "https://localhost:8443/api/telemetry/public/points"


def wait_for_readings() -> None:
    # Caddy uses its local development CA; this URL is fixed to loopback.
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    deadline = time.monotonic() + 120
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            with urllib.request.urlopen(URL, context=context, timeout=min(5, remaining)) as response:
                points = json.load(response)
            if (
                isinstance(points, list)
                and len(points) == 5
                and all(isinstance(point, dict) and point.get("updatedAt") for point in points)
            ):
                print("All five monitoring points have readings.")
                return
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass  # Startup failures are retried within the fixed deadline.
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    raise SystemExit("Timed out after 120 seconds waiting for five updated monitoring points.")


if __name__ == "__main__":
    wait_for_readings()
