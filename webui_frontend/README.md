# Route Graph WebUI Frontend

Vue/Vite frontend for `route_graph_webui`. Run commands from the project root with `npm --prefix webui_frontend ...`, or from this directory without the prefix.

## Environment

- `VITE_API_BASE`：optional backend base URL. Leave empty in dev mode to use the Vite `/api` proxy. Set it when the backend host or port differs from the default.
- `ROUTE_GRAPH_WEBUI_HOST` / `ROUTE_GRAPH_WEBUI_PORT`：used by `vite.config.ts` to target the backend proxy.
- `ROUTE_GRAPH_WEBUI_VITE_HOST`：Vite dev server host. Defaults to `127.0.0.1`, or `0.0.0.0` when `ROUTE_GRAPH_WEBUI_ALLOW_LAN=1`.

Example values are documented in `../.env.example`.

## Scripts

```powershell
npm run dev
npm test
npm run test:collect
npm run typecheck
npm run lint
npm run format
npm run build
```

- `typecheck` runs `vue-tsc -b`.
- `lint` runs lightweight source checks for conflict markers, `debugger`, focused tests, then runs `typecheck`.
- `format` is a check-mode script for final newline and trailing whitespace.
- `build` runs typecheck and Vite production build.

