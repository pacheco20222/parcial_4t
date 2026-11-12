def main() -> None:
    import os

    import uvicorn

    # Trust X-Forwarded-For only from the gateway's fixed IP (compose), never a subnet.
    gateway_ip = os.environ.get("GATEWAY_IP", "172.30.30.10")
    uvicorn.run(
        "telemetry_service.api:create_app",
        factory=True,
        root_path="/api/telemetry",
        host="0.0.0.0",
        port=8000,
        forwarded_allow_ips=gateway_ip,
        access_log=False,
        log_config=None,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
