from app.agent.playbook import build_playbook
from app.memory.redis_store import MemoryStore
from app.models import RunRequest, RunResponse
from app.services.metrics import record_run_metrics
from app.services.weave_stub import init_weave, trace_run, wandb_run, weave_op
import uuid


@weave_op()
def run_agent(payload: RunRequest, memory: MemoryStore) -> RunResponse:
    run_id = str(uuid.uuid4())
    init_weave()

    with wandb_run(run_id):
        preferences = memory.get_preferences()

        steps, notes = build_playbook(payload, preferences)

        # Placeholder: real integration will execute Browserbase steps.
        status = "completed"

        # Minimal learning behavior: persist a preference if provided in notes.
        for note in notes:
            if note.startswith("PREF:"):
                _, key, value = note.split(":", 2)
                memory.set_preference(key, value)

        trace_run(run_id, payload, steps, notes)
        record_run_metrics(run_id, steps, status)

        return RunResponse(run_id=run_id, status=status, steps=steps, notes=notes)
