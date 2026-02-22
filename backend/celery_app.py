from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable

from backend.core.config import get_settings

try:  # pragma: no cover - exercised when celery is installed
    from celery import Celery as _Celery
except ModuleNotFoundError:  # pragma: no cover - local/offline fallback
    _Celery = None

settings = get_settings()


class _LocalAsyncResult:
    def __init__(self, value: Any = None, error: Exception | None = None) -> None:
        self._value = value
        self._error = error

    def get(self, disable_sync_subtasks: bool = False) -> Any:  # noqa: ARG002 - keep celery-compatible signature
        if self._error:
            raise self._error
        return self._value


class _LocalTask:
    def __init__(self, fn: Callable[..., Any], *, bind: bool, name: str | None, max_retries: int) -> None:
        self._fn = fn
        self.bind = bind
        self.name = name or fn.__name__
        self.max_retries = max_retries
        self.request = SimpleNamespace(retries=0)
        self.app = SimpleNamespace()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.run(*args, **kwargs)

    def run(self, *args: Any, **kwargs: Any) -> Any:
        if self.bind:
            return self._fn(self, *args, **kwargs)
        return self._fn(*args, **kwargs)

    def apply_async(
        self,
        args: list[Any] | tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        queue: str | None = None,  # noqa: ARG002
        **_: Any,
    ) -> _LocalAsyncResult:
        call_args = tuple(args or ())
        call_kwargs = dict(kwargs or {})
        try:
            value = self.run(*call_args, **call_kwargs)
            return _LocalAsyncResult(value=value)
        except Exception as exc:
            return _LocalAsyncResult(error=exc)

    def retry(self, exc: Exception | None = None, countdown: int | None = None) -> None:  # noqa: ARG002
        if exc:
            raise exc
        raise RuntimeError("Task retry requested")


class _LocalCelery:
    def __init__(self, name: str) -> None:
        self.name = name
        self.conf: dict[str, Any] = {}

    def task(self, **task_options: Any):
        bind = bool(task_options.get("bind"))
        name = task_options.get("name")
        max_retries = int(task_options.get("max_retries") or 0)

        def decorator(fn: Callable[..., Any]) -> _LocalTask:
            return _LocalTask(fn, bind=bind, name=name, max_retries=max_retries)

        return decorator

    def autodiscover_tasks(self, modules: list[str]) -> None:  # noqa: ARG002
        return None


if _Celery is not None:
    celery_app = _Celery("fire")
else:  # pragma: no cover - only used in offline/dev mode without celery installed
    celery_app = _LocalCelery("fire")

celery_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=max(30, settings.celery_task_time_limit_seconds),
    task_soft_time_limit=max(15, settings.celery_task_soft_time_limit_seconds),
    task_routes={
        "backend.tasks.run.*": {"queue": "default"},
        "backend.tasks.ticket.*": {"queue": "default"},
        "backend.tasks.ai.*": {"queue": "ai"},
        "backend.tasks.geocode.*": {"queue": "geocode"},
        "backend.tasks.routing.*": {"queue": "routing"},
    },
)

celery_app.autodiscover_tasks(["backend.tasks"])
