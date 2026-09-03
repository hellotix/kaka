---
layout: doc
title: Frontend Development Guide
description: "Frontend dev guide: Vue3 + TypeScript + Element Plus, routing, state, API integration."
outline: "deep"
---

> For detailed structure, path aliases, and env config, see [frontend/web/README.md](https://github.com/fastapiadmin/FastapiAdmin/blob/master/frontend/web/README.md).

## Technology Stack

| Category | Choice |
|----------|--------|
| Framework | Vue 3 (Composition API / `<script setup>`) |
| Build | Vite 7 |
| Language | TypeScript |
| UI | Element Plus |
| Router | Vue Router 4 (Hash mode) |
| State | Pinia + pinia-plugin-persistedstate |
| Styles | Tailwind CSS 4, SCSS |
| HTTP | Axios |

## Project Structure

```
frontend/web/src/
├── api/              # API modules by business domain
├── assets/           # Images, fonts, global styles
├── components/       # Shared & business components
├── config/           # App configuration
├── enums/            # Enumerations
├── hooks/            # Composable functions
├── layouts/          # Layout system (left, top, mixed)
├── locales/          # i18n
├── plugins/          # Vue plugin registration
├── router/           # Static routes, dynamic routes, guards
├── store/            # Pinia modules
├── styles/           # Style system (including dark theme)
├── types/            # TypeScript types
├── utils/            # Utilities
├── views/            # Page views
├── App.vue
└── main.ts           # Entry
```

## Path Aliases

| Alias | Points to |
|-------|-----------|
| `@` | `src/` |
| `@views` | `src/views` |
| `@stores` | `src/store` |
| `@utils` | `src/utils` |

## Environment Variables

Only variables prefixed with `VITE_` are injected into frontend code:

| Variable | Purpose |
|----------|---------|
| `VITE_PORT` | Dev server port |
| `VITE_API_BASE_URL` | Proxy target: backend HTTP address |
| `VITE_APP_BASE_API` | API path prefix |
| `VITE_APP_WS_ENDPOINT` | WebSocket endpoint |
| `VITE_APP_TITLE` | Page title |
| `VITE_BASE_URL` | Deployment base path |
| `VITE_ACCESS_MODE` | Menu source (frontend / backend / mixed) |

**Restart** `pnpm dev` after changing env files.

## Scripts

```bash
cd frontend/web
pnpm install
pnpm dev              # Dev server (default 5173)

# Other scripts
pnpm build            # Production build
pnpm type-check       # TypeScript check
pnpm lint             # ESLint + Prettier + Stylelint
pnpm clean:cache      # Clean cache
```

## Routes & Menus

| File | Responsibility |
|------|---------------|
| `src/router/staticRoutes.ts` | Static routes, shell layout |
| `src/router/dynamicRoutes.ts` | Menu-driven dynamic routes |
| `src/router/beforeEach.ts` | Auth guard, dynamic mounting |
| `src/router/MenuProcessor.ts` | Backend menu → frontend routes |

Routes use **Hash mode**. Static routes (Layout/Login/404) register on load. Business routes are lazy `addRoute` by guard based on menu permissions.

## App Startup Flow

```
main.ts → initPlugins(app) → mount("#app")
  → App.vue → onBeforeMount: theme init
  → onMounted: bootstrap() → storage check/upgrade/site config
  → route guard beforeEach
    → storage invalidation check
    → auth check
    → dynamic route registration (menu → addRoute)
    → tab/title sync
```

## Adding a New Page

1. Create API file in `src/api/`
2. Create page component in `src/views/`
3. Register route (static or dynamic) + backend menu config
4. Keep path and name consistent across all three

## Common Issues

| Symptom | Suggestion |
|---------|-----------|
| `ECONNREFUSED` | Backend not running or wrong port |
| 401 / frequent login redirects | Token expired, clear local storage and re-login |
| `.env` changes not taking effect | Must restart `pnpm dev` |
| Dependency issues | Try `pnpm clean:cache && pnpm dev` |
| Type errors | Run `pnpm type-check` |

## Build & Deploy

- Output directory: `dist/`
- For sub-path deployment, set `VITE_BASE_URL`
- Production build may strip `console` (see `vite.config.ts`)
