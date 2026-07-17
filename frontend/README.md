# AI-SPM — Admin & Platform Dashboard

Enterprise dashboard for the **AI-SPM** (AI Security Posture Management) SaaS
platform. Built with **React + TypeScript + Vite + Tailwind CSS**, with
**TanStack Query** for server state and **Zustand** for in-memory auth.

## Consoles

| Console            | Routes                                                        | Auth token           |
| ------------------ | ------------------------------------------------------------ | -------------------- |
| **Tenant admin**   | `/login`, `/dashboard`, `/agents`, `/policies`, `/audit`     | `/admin/v1` JWT      |
| **Platform ops**   | `/platform/login`, `/platform/tenants`                        | `/platform/v1` JWT   |

Navigation items are permission-gated using the `permissions` claim embedded in
the JWT (mirrors the backend's `resource:*` wildcard semantics).

## Getting started

```bash
npm install
cp .env.example .env      # set VITE_API_URL if not using the default
npm run dev               # http://localhost:5173
```

The API base URL defaults to the Kong gateway at `http://localhost:8080` and is
configurable via `VITE_API_URL`.

### Default platform operator

After the backend's first boot: `platform-admin@aispm.io` / `PlatformAdmin123!`

## Scripts

| Command           | Description                                 |
| ----------------- | ------------------------------------------- |
| `npm run dev`     | Start the Vite dev server                   |
| `npm run build`   | Type-check and build the production bundle   |
| `npm run preview` | Preview the production build locally         |
| `npm run lint`    | Type-check without emitting                  |

## API contract

Endpoints consumed (see `src/lib/api.ts`) — all relative to `VITE_API_URL`:

- `POST /admin/v1/auth/login`, `GET /admin/v1/auth/me`
- `GET /admin/v1/agents`, `GET /admin/v1/audit`, `GET /admin/v1/policies`
- `POST /platform/v1/auth/login`
- `GET /platform/v1/tenants`, `POST /platform/v1/tenants/{id}/suspend|activate`

## Docker

The image builds the static SPA and serves it via nginx with SPA history
fallback, gzip, asset caching, and security headers.

```bash
docker build -t ai-spm-dashboard \
  --build-arg VITE_API_URL=https://api.aispm.io .
docker run -p 8080:80 ai-spm-dashboard
```

> `VITE_API_URL` is baked at **build time** (Vite inlines env vars). Rebuild the
> image to point at a different API origin.

## Project structure

```
src/
├── components/       # layout (sidebar, main), UI primitives, route guards
├── hooks/            # TanStack Query hooks
├── lib/              # API client, JWT decode, utils
├── pages/            # route views (admin + platform)
├── stores/           # Zustand auth store (JWT in memory)
└── types/            # API type definitions (mirror backend schemas)
```
