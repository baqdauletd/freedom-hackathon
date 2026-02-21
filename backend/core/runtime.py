from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

APP_INSTANCE_ID = str(uuid4())
APP_STARTED_AT = datetime.now(UTC)

