from contextlib import contextmanager
from typing import Callable, Iterator

from app.core.config import settings
from app.models import RunRequest

try:
    import weave  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    weave = None

try:
    import wandb  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    wandb = None


def init_weave() -> None:
    if weave and settings.weave_project:
        weave.init(settings.weave_project)


def weave_op() -> Callable:
    if weave:
        return weave.op()

    def _identity(fn: Callable) -> Callable:
        return fn

    return _identity


@contextmanager
def wandb_run(run_id: str) -> Iterator[None]:
    if wandb and settings.wandb_project:
        run = wandb.init(
            project=settings.wandb_project,
            entity=settings.wandb_entity or None,
            name=f"run-{run_id}",
        )
        try:
            yield
        finally:
            run.finish()
    else:
        yield


def trace_run(run_id: str, payload: RunRequest, steps: list[str], notes: list[str]) -> None:
    _ = (run_id, payload, steps, notes)
