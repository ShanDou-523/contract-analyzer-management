"""Standalone durable background worker entry point for service deployments."""

from config import settings
from database import init_db
from services.background_worker import BackgroundWorker


def main() -> None:
    init_db()
    worker = BackgroundWorker(
        poll_seconds=settings.background_worker_poll_seconds,
        lock_timeout_seconds=settings.background_job_lock_timeout_seconds,
        provider_name=settings.notification_provider,
    )
    try:
        worker.run_forever()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == "__main__":
    main()
