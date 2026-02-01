# Ghost Mode Browser Agent (Python)

Minimal Python-first scaffold for a self-improving browser agent.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Electron frontend (React)

```bash
cd electron
npm install
npm run dev
```

## Env

Copy `.env.example` to `.env` and fill values as you integrate services.

W&B / Weave:
- Set `WEAVE_PROJECT` to enable tracing.
- Optionally set `WANDB_PROJECT` (and `WANDB_ENTITY`) to create a W&B run per API call.
