# Repository Guidelines

## Project Structure & Module Organization
- `backend/` FastAPI service (Python). Key files: `backend/app/main.py`, `backend/app/azure_clients.py`, `backend/app/prompt_templates.py`, scripts in `backend/scripts/`.
- `frontend/` React + Vite app (TypeScript). Entry: `frontend/src/main.tsx`, pages in `frontend/src/pages/`.
- `frontend/vite.config.ts` proxies `/api` → `http://localhost:8000` for local dev.
- Secrets live in `backend/.env` (see `backend/.env.example`). Do not commit real keys.

## Build, Test, and Development Commands
- Backend (venv + dev server):
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -r backend/requirements.txt`
  - `uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000`
- Frontend:
  - `cd frontend && npm install`
  - `npm run dev` (http://localhost:5173)
  - `npm run build` → outputs `frontend/dist/`; `npm run preview` to serve build
- Quick checks:
  - `python backend/scripts/aoai_health.py` (Azure OpenAI health)
  - `python backend/scripts/tts_gen.py` then `curl -X POST -F 'file=@/tmp/onboard_zh.wav' http://127.0.0.1:8000/api/onboard`
- Docker (backend): `cd backend && docker build -t voice-agent-backend:latest . && docker run --env-file ./.env -p 8000:8000 voice-agent-backend:latest`

## Coding Style & Naming Conventions
- Python: PEP 8, 4-space indent, type hints where practical. snake_case for functions/modules, PascalCase for classes. Keep modules in `backend/app/` small and focused.
- TypeScript/React: strict TypeScript (`frontend/tsconfig.json`). PascalCase component files in `src/pages/` (e.g., `Chat.tsx`), camelCase functions/variables, UPPER_SNAKE_CASE constants.
- Imports: group stdlib/vendor/local; avoid unused imports. No formatting tools are enforced; avoid large reformat-only diffs.

## Testing Guidelines
- No formal test suite yet. Prefer reproducible checks via scripts and HTTP calls:
  - Chat: `curl -X POST http://127.0.0.1:8000/api/agents/<id>/chat -H 'Content-Type: application/json' -d '{"message":"hi"}'`
- If adding tests, use `backend/tests/test_*.py` (pytest) and `frontend/src/__tests__/*.test.tsx` (Vitest/RTL). Keep tests hermetic and fast.

## Commit & Pull Request Guidelines
- Use Conventional Commits style: `feat(frontend): ...`, `fix(backend): ...`, `docs: ...`.
- PRs: include purpose, scope (backend/frontend), setup steps, and evidence (logs, screenshots, or sample `curl`). Link related issues. Keep PRs focused and under ~300 lines when possible.

## Security & Configuration Tips
- Never commit secrets. Copy `backend/.env.example` → `backend/.env` locally. Required keys: Azure OpenAI and Speech; region like `australiaeast` (no spaces). Configure `CORS_ORIGINS` for the frontend origin.
- Do not edit `frontend/dist/` by hand; it is build output.

## Agent-Specific Instructions
- Scope: root of this repository. When modifying code, prefer minimal, targeted patches, preserve existing structure and proxy behavior, and update docs if commands change. Avoid introducing new global dependencies without discussion.

