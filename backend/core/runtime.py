from __future__ import annotations

from datetime import timezone, datetime
from uuid import uuid4

UTC = timezone.utc
APP_INSTANCE_ID = str(uuid4())
APP_STARTED_AT = datetime.now(UTC)

