"""Entrypoint for the Lychee GitHub App webhook server.

Reads required configuration from environment variables, constructs an
``AppConfig``, creates the Starlette ASGI application via the webhook
module, and runs it under uvicorn.
"""

from __future__ import annotations

import os
import sys

import uvicorn

from lychee.config import AppConfig
from lychee.webhook import create_webhook_app


def load_app_config() -> AppConfig:
    """Load AppConfig from environment variables.

    Required env vars: LYCHEE_WEBHOOK_SECRET, LYCHEE_APP_ID, LYCHEE_PRIVATE_KEY_PATH.
    Raises SystemExit with a clear message if any required var is missing.
    """
    required_vars = ["LYCHEE_WEBHOOK_SECRET", "LYCHEE_APP_ID", "LYCHEE_PRIVATE_KEY_PATH"]
    missing = [v for v in required_vars if not os.environ.get(v)]

    if missing:
        print(
            f"Error: missing required environment variables: {', '.join(sorted(missing))}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return AppConfig(
        webhook_secret=os.environ["LYCHEE_WEBHOOK_SECRET"],
        app_id=int(os.environ["LYCHEE_APP_ID"]),
        private_key_path=os.environ["LYCHEE_PRIVATE_KEY_PATH"],
        host=os.environ.get("LYCHEE_HOST", "0.0.0.0"),
        port=int(os.environ.get("LYCHEE_PORT", "8000")),
        queue_workers=int(os.environ.get("LYCHEE_QUEUE_WORKERS", "4")),
        queue_max_size=int(os.environ.get("LYCHEE_QUEUE_MAX_SIZE", "100")),
        state_backend=os.environ.get("LYCHEE_STATE_BACKEND", "sqlite"),
        state_dsn=os.environ.get("LYCHEE_STATE_DSN", "lychee_state.db"),
    )


def main() -> None:
    """Load config, create the ASGI app, and run uvicorn."""
    config = load_app_config()
    app = create_webhook_app(config)
    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
