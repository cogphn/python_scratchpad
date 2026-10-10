# stview

A small Flask web UI for managing a local [SpacetimeDB](https://spacetimedb.com) instance.
Built with 100% pure vibedev and 0% love or professional engineering care.
 
## Features

- **Dashboard** – server reachability, active identity, database overview
- **Databases** – list databases owned by your identity (plus any you track by name), publish new
  modules (Wasm or TypeScript/JS bundles), add names, delete
- **Tables** – schema (columns, types, primary keys, indexes, constraints) and paginated row data
  with human-readable rendering of SATS values (identities, timestamps, options, enums, nested structs)
- **SQL console** – run ad-hoc queries
- **Reducers** – inspect signatures and invoke them with JSON arguments
- **Logs** – tail module logs
- Light/dark theme

## Running

```bash
uv run main.py          # http://127.0.0.1:5000
```

Environment variables:

| Variable            | Default                  | Purpose                                   |
| ------------------- | ------------------------ | ----------------------------------------- |
| `STVIEW_HOST`       | `http://127.0.0.1:3000`  | SpacetimeDB server URL                    |
| `STVIEW_TOKEN`      | –                        | Auth token to use (see below)             |
| `STVIEW_PORT`       | `5000`                   | Port for the web UI                       |
| `STVIEW_BIND`       | `127.0.0.1`              | Bind address for the web UI               |
| `STVIEW_CONFIG_DIR` | `~/.config/stview`       | Where `config.json` is stored             |

## Identity & tokens

SpacetimeDB has no "list every database" endpoint – it lists databases **owned by an identity**.
On first start stview picks a token in this order:

1. `STVIEW_TOKEN`
2. The `spacetime` CLI login in `~/.config/spacetime/cli.toml` (`spacetime login --server-issued-login local`)
3. A fresh identity minted from the server (saved to `~/.config/stview/config.json`)

Databases owned by other identities can still be browsed (public tables only) by adding them on the
Databases page with **Track database**.

## Layout

```
main.py                 entry point
stview/__init__.py      app factory, identity bootstrap
stview/client.py        SpacetimeDB HTTP API client
stview/sats.py          schema parsing + SATS-JSON value formatting
stview/settings.py      persistent config
stview/views.py         routes
stview/templates/       Jinja templates (Bootstrap 5 + Feather)
stview/static/          CSS / JS
```
