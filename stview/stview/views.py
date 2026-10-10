"""HTTP routes for stview."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import (
    Blueprint, Flask, abort, flash, g, redirect, render_template, request, url_for,
)

from . import ensure_identity
from .client import DatabaseInfo, SpacetimeClient, SpacetimeError
from .sats import ModuleSchema, ResultSet, parse_result, parse_schema

bp = Blueprint("ui", __name__)

ROW_LIMITS = (25, 50, 100, 250, 500, 1000)


# ------------------------------------------------------------------ helpers
def _client() -> SpacetimeClient:
    return g.client


def _load_database(ref: str) -> DatabaseInfo:
    try:
        return _client().database_info(ref)
    except SpacetimeError as e:
        if e.status == 404:
            abort(404, f"Database '{ref}' was not found on the server.")
        raise


def _load_schema(ref: str) -> ModuleSchema:
    return parse_schema(_client().schema(ref))


def _list_databases() -> tuple[list[DatabaseInfo], list[str]]:
    """Return (databases, errors). Combines owned + manually tracked DBs."""
    client = _client()
    settings = g.settings
    errors: list[str] = []
    refs: list[str] = []
    if settings.identity:
        try:
            refs.extend(client.databases_owned_by(settings.identity))
        except SpacetimeError as e:
            errors.append(f"Could not list databases owned by {settings.identity[:12]}…: {e}")
    refs.extend(settings.tracked_databases)

    seen: set[str] = set()
    out: list[DatabaseInfo] = []
    for ref in refs:
        try:
            info = client.database_info(ref)
        except SpacetimeError as e:
            errors.append(f"{ref}: {e}")
            continue
        if info.identity in seen:
            continue
        seen.add(info.identity)
        out.append(info)
    out.sort(key=lambda d: d.display_name.lower())
    return out, errors


def _row_counts(ref: str, schema: ModuleSchema) -> None:
    """Populate ``row_count`` on each table (the server only accepts one statement per request)."""
    client = _client()
    for t in schema.tables:
        try:
            t.row_count = _count_from(client.sql(ref, f"SELECT COUNT(*) AS n FROM {t.name}")[0])
        except SpacetimeError:
            t.row_count = None


def _count_from(stmt: dict) -> int | None:
    rows = stmt.get("rows") or []
    if not rows:
        return 0
    first = rows[0]
    if isinstance(first, list) and first:
        v = first[0]
    elif isinstance(first, dict):
        v = next(iter(first.values()), None)
    else:
        v = first
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _error(e: Exception) -> str:
    return str(e)


# ------------------------------------------------------------------- filters
def register_filters(app: Flask) -> None:
    @app.template_filter("short_id")
    def short_id(value: str | None, n: int = 8) -> str:
        if not value:
            return ""
        return f"{value[:n]}…{value[-6:]}" if len(value) > n + 8 else value

    @app.template_filter("pretty_json")
    def pretty_json(value) -> str:
        return json.dumps(value, indent=2, sort_keys=False)

    @app.template_filter("log_time")
    def log_time(value) -> str:
        if value is None:
            return ""
        if isinstance(value, (int, float)):
            # micros or millis or seconds – guess from magnitude
            ts = float(value)
            if ts > 1e15:
                ts /= 1e6
            elif ts > 1e12:
                ts /= 1e3
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    @app.context_processor
    def inject_globals():
        return {"settings": g.get("settings"), "row_limits": ROW_LIMITS}


# -------------------------------------------------------------------- errors
@bp.app_errorhandler(SpacetimeError)
def handle_spacetime_error(e: SpacetimeError):
    status = 502 if e.status is None else (e.status if e.status in (401, 403, 404) else 502)
    return render_template("error.html", title="SpacetimeDB error", message=str(e), status=status), status


@bp.app_errorhandler(404)
def handle_404(e):
    return render_template("error.html", title="Not found", message=getattr(e, "description", str(e)), status=404), 404


# ----------------------------------------------------------------- dashboard
@bp.route("/")
def dashboard():
    client = _client()
    online = client.ping()
    databases: list[DatabaseInfo] = []
    errors: list[str] = []
    identity_ok = None
    if online:
        databases, errors = _list_databases()
        if g.settings.identity:
            identity_ok = client.verify_identity(g.settings.identity)
    return render_template(
        "dashboard.html", online=online, databases=databases, errors=errors, identity_ok=identity_ok,
    )


# ----------------------------------------------------------------- databases
@bp.route("/databases")
def databases():
    dbs, errors = _list_databases()
    # Table counts per database (best effort, cheap on a local server).
    table_counts: dict[str, int | None] = {}
    for db in dbs:
        try:
            table_counts[db.identity] = len(_load_schema(db.identity).tables)
        except SpacetimeError:
            table_counts[db.identity] = None
    return render_template("databases.html", databases=dbs, errors=errors, table_counts=table_counts)


@bp.post("/databases/track")
def track_database():
    ref = (request.form.get("ref") or "").strip()
    if not ref:
        flash("Enter a database name or identity.", "warning")
        return redirect(url_for("ui.databases"))
    try:
        info = _client().database_info(ref)
    except SpacetimeError as e:
        flash(f"Could not find database '{ref}': {e}", "danger")
        return redirect(url_for("ui.databases"))
    if g.settings.track(ref):
        flash(f"Now tracking {info.display_name}.", "success")
    else:
        flash(f"{info.display_name} is already tracked.", "info")
    return redirect(url_for("ui.database", ref=info.ref))


@bp.post("/databases/<ref>/untrack")
def untrack_database(ref: str):
    removed = g.settings.untrack(ref)
    # Also untrack by any alias of this database.
    try:
        info = _client().database_info(ref)
        for alias in [info.identity, *(info.names or [])]:
            removed = g.settings.untrack(alias) or removed
    except SpacetimeError:
        pass
    flash("Stopped tracking database." if removed else "Database was not tracked.", "info")
    return redirect(url_for("ui.databases"))


@bp.route("/db/<ref>")
def database(ref: str):
    info = _load_database(ref)
    schema_error = None
    schema = None
    try:
        schema = _load_schema(info.identity)
        _row_counts(info.identity, schema)
    except SpacetimeError as e:
        schema_error = _error(e)
    is_owner = bool(g.settings.identity) and g.settings.identity == info.owner_identity
    tracked = any(r in g.settings.tracked_databases for r in [ref, info.identity, *(info.names or [])])
    return render_template(
        "database.html", db=info, schema=schema, schema_error=schema_error, is_owner=is_owner,
        tracked=tracked, ref=ref,
    )


@bp.post("/db/<ref>/delete")
def delete_database(ref: str):
    info = _load_database(ref)
    if request.form.get("confirm") != info.display_name:
        flash("Confirmation text did not match – database was not deleted.", "warning")
        return redirect(url_for("ui.database", ref=ref))
    try:
        _client().delete_database(info.identity)
    except SpacetimeError as e:
        flash(f"Delete failed: {e}", "danger")
        return redirect(url_for("ui.database", ref=ref))
    for alias in [info.identity, *(info.names or [])]:
        g.settings.untrack(alias)
    flash(f"Deleted database {info.display_name}.", "success")
    return redirect(url_for("ui.databases"))


@bp.post("/db/<ref>/names")
def add_name(ref: str):
    info = _load_database(ref)
    new_name = (request.form.get("name") or "").strip()
    if not new_name:
        flash("Enter a name.", "warning")
        return redirect(url_for("ui.database", ref=ref))
    try:
        result = _client().add_database_name(info.identity, new_name)
    except SpacetimeError as e:
        flash(f"Could not add name: {e}", "danger")
        return redirect(url_for("ui.database", ref=ref))
    if isinstance(result, dict) and "PermissionDenied" in result:
        flash(f"Permission denied: the name '{new_name}' is owned by someone else.", "danger")
        return redirect(url_for("ui.database", ref=ref))
    flash(f"Added name '{new_name}'.", "success")
    return redirect(url_for("ui.database", ref=new_name))


# -------------------------------------------------------------------- tables
@bp.route("/db/<ref>/table/<table>")
def table(ref: str, table: str):
    info = _load_database(ref)
    schema = _load_schema(info.identity)
    tdef = schema.table(table)
    if tdef is None:
        abort(404, f"Table '{table}' does not exist in {info.display_name}.")
    try:
        limit = int(request.args.get("limit", 100))
    except ValueError:
        limit = 100
    limit = max(1, min(limit, 5000))

    result: ResultSet | None = None
    error = None
    truncated = False
    client = _client()
    try:
        stmts = client.sql(info.identity, f"SELECT * FROM {table} LIMIT {limit}")
        result = parse_result(stmts[0], schema.typespace) if stmts else None
    except SpacetimeError as e:
        # Older servers may not support LIMIT; fall back and truncate locally.
        try:
            stmts = client.sql(info.identity, f"SELECT * FROM {table}")
            result = parse_result(stmts[0], schema.typespace) if stmts else None
            if result and len(result.rows) > limit:
                truncated = True
                result.rows = result.rows[:limit]
        except SpacetimeError as e2:
            error = _error(e2 if e2.status != 400 else e)
    try:
        count_stmt = client.sql(info.identity, f"SELECT COUNT(*) AS n FROM {table}")
        tdef.row_count = _count_from(count_stmt[0])
    except SpacetimeError:
        tdef.row_count = None
    return render_template(
        "table.html", db=info, ref=ref, schema=schema, table=tdef, result=result, error=error,
        limit=limit, truncated=truncated,
    )


# ----------------------------------------------------------------------- sql
@bp.route("/db/<ref>/sql", methods=["GET", "POST"])
def sql(ref: str):
    info = _load_database(ref)
    schema = None
    try:
        schema = _load_schema(info.identity)
    except SpacetimeError:
        pass
    query = request.form.get("query") or request.args.get("q") or ""
    results: list[ResultSet] = []
    error = None
    if request.method == "POST" and query.strip():
        try:
            stmts = _client().sql(info.identity, query)
            ts = schema.typespace if schema else None
            results = [parse_result(s, ts) for s in stmts]
        except SpacetimeError as e:
            error = _error(e)
    return render_template(
        "sql.html", db=info, ref=ref, schema=schema, query=query, results=results, error=error,
    )


# ---------------------------------------------------------------------- logs
@bp.route("/db/<ref>/logs")
def logs(ref: str):
    info = _load_database(ref)
    try:
        num = int(request.args.get("n", 200))
    except ValueError:
        num = 200
    num = max(10, min(num, 5000))
    entries: list[dict] = []
    error = None
    try:
        entries = _client().logs(info.identity, num)
    except SpacetimeError as e:
        error = _error(e)
    entries.reverse()  # newest first
    return render_template("logs.html", db=info, ref=ref, entries=entries, error=error, num=num)


# ------------------------------------------------------------------ reducers
@bp.post("/db/<ref>/call/<reducer>")
def call_reducer(ref: str, reducer: str):
    info = _load_database(ref)
    raw = (request.form.get("args") or "[]").strip() or "[]"
    try:
        args = json.loads(raw)
        if not isinstance(args, list):
            raise ValueError("arguments must be a JSON array")
    except ValueError as e:
        flash(f"Invalid arguments: {e}", "danger")
        return redirect(url_for("ui.database", ref=ref, _anchor="reducers"))
    try:
        _client().call_reducer(info.identity, reducer, args)
    except SpacetimeError as e:
        flash(f"Reducer '{reducer}' failed: {e}", "danger")
        return redirect(url_for("ui.database", ref=ref, _anchor="reducers"))
    flash(f"Called reducer '{reducer}' successfully.", "success")
    return redirect(url_for("ui.database", ref=ref, _anchor="reducers"))


# ------------------------------------------------------------------- publish
@bp.route("/publish", methods=["GET", "POST"])
def publish():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip() or None
        clear = request.form.get("clear") == "on"
        file = request.files.get("module")
        if file is None or not file.filename:
            flash("Choose a .wasm or .js module to publish.", "warning")
            return redirect(url_for("ui.publish"))
        data = file.read()
        host_type = request.form.get("host_type") or "auto"
        if host_type == "auto":
            host_type = "Wasm" if data[:4] == b"\x00asm" else "Js"
        if host_type == "Wasm" and data[:4] != b"\x00asm":
            flash("That file does not look like a WebAssembly binary (missing \\0asm magic).", "danger")
            return redirect(url_for("ui.publish"))
        try:
            result = _client().publish(data, name=name, clear=clear, host_type=host_type)
        except SpacetimeError as e:
            flash(f"Publish failed: {e}", "danger")
            return redirect(url_for("ui.publish"))
        if isinstance(result, dict) and "Success" in result:
            s = result["Success"]
            ident = s.get("database_identity")
            op = s.get("op", "published")
            if not name and ident:
                g.settings.track(ident)
            flash(f"Database {name or ident} {op}.", "success")
            return redirect(url_for("ui.database", ref=name or ident))
        flash(f"Unexpected response: {result}", "warning")
        return redirect(url_for("ui.publish"))
    return render_template("publish.html")


# ------------------------------------------------------------------ settings
@bp.route("/settings", methods=["GET", "POST"])
def settings_view():
    s = g.settings
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save":
            host = (request.form.get("host") or "").strip().rstrip("/")
            token = (request.form.get("token") or "").strip()
            if host:
                s.host = host
            if token and token != s.token:
                s.token = token
                s.identity = None
                s.token_source = "entered in settings"
            ensure_identity(s)
            s.save()
            flash("Settings saved.", "success")
        elif action == "new_identity":
            try:
                data = SpacetimeClient(s.host).create_identity()
            except SpacetimeError as e:
                flash(f"Could not create identity: {e}", "danger")
                return redirect(url_for("ui.settings_view"))
            s.token, s.identity, s.token_source = data["token"], data["identity"], "generated by stview"
            s.save()
            flash("Created a fresh identity.", "success")
        elif action == "use_cli":
            s.token = None
            s.identity = None
            s.token_source = None
            ensure_identity(s)
            flash("Reloaded identity from the spacetime CLI config.", "success")
        return redirect(url_for("ui.settings_view"))
    client = _client()
    online = client.ping()
    identity_ok = client.verify_identity(s.identity) if (online and s.identity) else None
    return render_template("settings.html", online=online, identity_ok=identity_ok)
