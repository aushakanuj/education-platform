# Frontend

Vite + React + TypeScript student web client for the education platform POC.

Designed in Hallmark **Hum** (playful-technical) with a **Narrative Workflow** study path:
enroll → study → quiz → result.

## Prerequisites

- Node 18+ (20+ preferred)
- API running at `http://127.0.0.1:8000` (see repo root README)

## Setup

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173`.

## Scripts

| Command | Purpose |
| --- | --- |
| `npm run dev` | Dev server on port 5173 |
| `npm run build` | Typecheck + production build |
| `npm test` | Vitest unit/component tests |
| `npm run preview` | Preview production build |

## POC flow

1. **Create student** or **Sign in** on `/login`
2. **Enroll** in Grade 8 Math (`POST /api/v1/me/enrollments/poc-math`)
3. Open a topic lesson, then **Start the quiz**
4. Submit answers; review score (pass ≥ 70%). Correct option labels are never shown.
