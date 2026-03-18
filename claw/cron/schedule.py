from datetime import datetime, timezone
from croniter import croniter


def next_run_dt(cron_expr: str, after: datetime | None = None) -> datetime:
    """Return next execution time (UTC)."""
    base = after or datetime.now(timezone.utc)
    it = croniter(cron_expr, base)
    return it.get_next(datetime).replace(tzinfo=timezone.utc)
