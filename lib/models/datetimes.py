"""The timestamp type every API response should use.

SQLite has no timezone storage. The columns are declared
``DateTime(timezone=True)`` and the app writes ``datetime.now(timezone.utc)``,
but what comes back out is naive -- the offset is dropped on the way in. Pydantic
then serialised that naive value verbatim, so the API said

    "started_at": "2026-09-13T22:42:35.474942"

for an instant that is UTC, without saying so. Every consumer then had to know
by other means. The Streamlit dashboard did (``pd.to_datetime(..., utc=True)``);
the React app did not, and ``new Date()`` reads a bare datetime as *local* time.

On a machine four hours behind UTC that put every timestamp four hours in the
future, which is invisible in "3 days ago" and very visible in a progress bar:
elapsed came out negative, so bars rendered empty and the estimate read
"About 4 h 8 min left" -- the budget plus the offset.

Attaching UTC here fixes it for every consumer at once, because it makes the
response state the thing that was previously assumed.
"""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator


def _assume_utc(value: datetime) -> datetime:
    """Mark a naive timestamp as UTC, which is what it already was.

    Only naive values are touched. Anything that arrives with an offset came
    from somewhere that already knew, and is left as it is.
    """
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


UtcDatetime = Annotated[datetime, AfterValidator(_assume_utc)]
