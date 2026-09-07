#!/usr/bin/env python3
"""Elastic Stack Rebuild Asset Automation Tool.

Automates the installation and verification of integration assets for:
  - Windows (`windows`)
  - Elastic Defend / Endpoint Security (`endpoint`)
  - Fortinet FortiGate (`fortinet_fortigate`)
  - Palo Alto Next-Gen Firewall (`panw`)

Features:
  1. Health-check & retry wait loop for newly rebuilt Kibana/ES instances.
  2. Fleet initialization (`POST /api/fleet/setup`).
  3. Dynamic version resolution and asset installation via Fleet EPM API
     (`POST /api/fleet/epm/packages/{pkg}/{version}`).
  4. Prepackaged security detection rules initialization.
  5. Live asset verification across index templates, ingest pipelines, and dashboards.
  6. Offline asset bundle export and import for air-gapped environments.
"""

import argparse
import datetime
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import requests
import urllib3
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

console = Console()

DEFAULT_PACKAGES = [
    {"name": "windows", "title": "Windows", "default_version": "3.9.5"},
    {"name": "endpoint", "title": "Elastic Defend", "default_version": "9.4.1"},
    {"name": "fortinet_fortigate", "title": "Fortinet FortiGate Firewall Logs", "default_version": "1.36.10"},
    {"name": "panw", "title": "Palo Alto Next-Gen Firewall", "default_version": "5.5.0"},
]

KEY_DATA_STREAMS = {
    "windows": ["logs-windows.forwarded-default", "logs-windows.powershell-default", "logs-windows.sysmon_operational-default"],
    "endpoint": [
        "logs-endpoint.events.process-default",
        "logs-endpoint.events.network-default",
        "logs-endpoint.events.file-default",
        "logs-endpoint.events.registry-default",
        "logs-endpoint.events.library-default",
        "logs-endpoint.alerts-default",
    ],
    "fortinet_fortigate": ["logs-fortinet_fortigate.log-default"],
    "panw": ["logs-panw.panos-default"],
}

VERIFICATION_TARGETS = {
    "windows": {
        "index_templates": ["logs-windows.forwarded", "logs-windows.powershell", "logs-windows.sysmon_operational"],
        "pipelines": ["logs-windows.forwarded-3.9.5", "logs-windows.powershell-3.9.5"],
        "dashboard_prefix": "windows-",
    },
    "endpoint": {
        "index_templates": [
            "logs-endpoint.events.process",
            "logs-endpoint.events.network",
            "logs-endpoint.events.file",
            "logs-endpoint.events.registry",
            "logs-endpoint.events.library",
            "logs-endpoint.alerts",
        ],
        "pipelines": [
            "logs-endpoint.events.process-9.4.1",
            "logs-endpoint.events.network-9.4.1",
            "logs-endpoint.events.file-9.4.1",
            "logs-endpoint.events.registry-9.4.1",
            "logs-endpoint.events.library-9.4.1",
            "logs-endpoint.alerts-9.4.1",
        ],
        "dashboard_prefix": "endpoint",
    },
    "fortinet_fortigate": {
        "index_templates": ["logs-fortinet_fortigate.log"],
        "pipelines": [
            "logs-fortinet_fortigate.log-1.36.10",
            "logs-fortinet_fortigate.log-1.36.10-traffic",
            "logs-fortinet_fortigate.log-1.36.10-event",
            "logs-fortinet_fortigate.log-1.36.10-login",
            "logs-fortinet_fortigate.log-1.36.10-utm",
        ],
        "dashboard_prefix": "fortinet_fortigate-",
    },
    "panw": {
        "index_templates": ["logs-panw.panos"],
        "pipelines": [
            "logs-panw.panos-5.5.0",
            "logs-panw.panos-5.5.0-traffic",
            "logs-panw.panos-5.5.0-threat",
            "logs-panw.panos-5.5.0-system",
        ],
        "dashboard_prefix": "panw-",
    },
}


def load_env() -> Dict[str, str]:
    """Reads configuration from local dotenv files."""
    config: Dict[str, str] = {}
    for env_file in [".env", ".env_googledev"]:
        if os.path.exists(env_file):
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            config[k.strip()] = v.strip()
            except Exception:
                pass
    return config


class IntegrationAssetInstaller:
    """Manages integration packages and assets in Kibana and Elasticsearch."""

    def __init__(
        self,
        kibana_url: str,
        api_key: str,
        es_url: Optional[str] = None,
        verify_ssl: bool = False,
        timeout: int = 45,
    ):
        self.kibana_url = kibana_url.rstrip("/")
        self.api_key = api_key
        self.es_url = es_url.rstrip("/") if es_url else None
        self.verify_ssl = verify_ssl
        self.timeout = timeout

        self.kbn_headers = {
            "Authorization": f"ApiKey {self.api_key}",
            "kbn-xsrf": "true",
            "Content-Type": "application/json",
            "User-Agent": "Elastic-Asset-Installer/1.0",
        }

        self.es_headers = {
            "Authorization": f"ApiKey {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Elastic-Asset-Installer/1.0",
        }

    def wait_for_kibana_ready(self, max_wait_seconds: int = 120, poll_interval: int = 5) -> bool:
        """Polls Kibana status API until Kibana is reachable and reporting OK."""
        console.print(f"[bold cyan][*][/bold cyan] Checking Kibana readiness at {self.kibana_url}...")
        start_time = time.time()
        url = f"{self.kibana_url}/api/status"

        while time.time() - start_time < max_wait_seconds:
            try:
                resp = requests.get(url, headers=self.kbn_headers, verify=self.verify_ssl, timeout=self.timeout)
                if resp.status_code == 200:
                    status_data = resp.json().get("status", {})
                    overall = status_data.get("overall", {}).get("level", "unknown")
                    v = resp.json().get("version", {}).get("number", "unknown")
                    console.print(f"[bold green][+][/bold green] Kibana v{v} is ready (Status: {overall})")
                    return True
                else:
                    console.print(f"[yellow][!][/yellow] Kibana returned HTTP {resp.status_code}. Waiting {poll_interval}s...")
            except Exception as e:
                console.print(f"[yellow][!][/yellow] Kibana not reachable yet ({type(e).__name__}). Waiting {poll_interval}s...")

            time.sleep(poll_interval)

        console.print(f"[bold red][-][/bold red] Timed out waiting for Kibana after {max_wait_seconds}s")
        return False

    def initialize_fleet(self) -> bool:
        """Calls POST /api/fleet/setup to initialize Fleet system indices and configs."""
        console.print("[bold cyan][*][/bold cyan] Initializing Fleet in Kibana (`POST /api/fleet/setup`)...")
        url = f"{self.kibana_url}/api/fleet/setup"

        try:
            resp = requests.post(url, headers=self.kbn_headers, json={}, verify=self.verify_ssl, timeout=self.timeout)
            if resp.status_code in (200, 201):
                data = resp.json()
                is_init = data.get("isInitialized", True)
                console.print(f"[bold green][+][/bold green] Fleet initialized successfully (isInitialized={is_init})")
                return True
            else:
                console.print(f"[bold red][-][/bold red] Fleet setup failed ({resp.status_code}): {resp.text[:300]}")
                return False
        except Exception as e:
            console.print(f"[bold red][-][/bold red] Request error during Fleet setup: {e}")
            return False

    def get_package_info(self, package_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves package metadata and installation state from /api/fleet/epm/packages/{pkg}."""
        url = f"{self.kibana_url}/api/fleet/epm/packages/{package_name}"
        try:
            resp = requests.get(url, headers=self.kbn_headers, verify=self.verify_ssl, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json().get("item", {})
            return None
        except Exception as e:
            console.print(f"[bold red][-][/bold red] Error fetching package info for '{package_name}': {e}")
            return None

    def install_package(self, package_name: str, version: Optional[str] = None, force: bool = True) -> Dict[str, Any]:
        """Installs the integration package and all its assets via Fleet EPM API."""
        # 1. Resolve version
        pkg_info = self.get_package_info(package_name)
        resolved_version = version
        if not resolved_version and pkg_info:
            resolved_version = pkg_info.get("version") or pkg_info.get("latestVersion")

        if not resolved_version:
            for default_pkg in DEFAULT_PACKAGES:
                if default_pkg["name"] == package_name:
                    resolved_version = default_pkg["default_version"]
                    break

        if not resolved_version:
            return {"success": False, "package": package_name, "error": "Unable to resolve package version"}

        url = f"{self.kibana_url}/api/fleet/epm/packages/{package_name}/{resolved_version}"
        payload = {"force": force}

        console.print(f"[bold cyan][*][/bold cyan] Installing package [bold]{package_name}@{resolved_version}[/bold] (force={force})...")
        try:
            resp = requests.post(url, headers=self.kbn_headers, json=payload, verify=self.verify_ssl, timeout=90)
            if resp.status_code in (200, 201):
                items = resp.json().get("items", [])
                es_assets = [i for i in items if i.get("type") in ("ingest_pipeline", "index_template", "component_template")]
                kbn_assets = [i for i in items if i.get("type") not in ("ingest_pipeline", "index_template", "component_template")]
                console.print(
                    f"[bold green][+][/bold green] [bold]{package_name}@{resolved_version}[/bold] installed: "
                    f"[cyan]{len(items)} total assets[/cyan] ([green]{len(es_assets)} ES[/green], [magenta]{len(kbn_assets)} Kibana[/magenta])"
                )
                return {
                    "success": True,
                    "package": package_name,
                    "version": resolved_version,
                    "total_assets": len(items),
                    "es_assets": len(es_assets),
                    "kibana_assets": len(kbn_assets),
                    "items": items,
                }
            else:
                err = resp.text[:300]
                console.print(f"[bold red][-][/bold red] Package installation failed for {package_name} ({resp.status_code}): {err}")
                return {"success": False, "package": package_name, "version": resolved_version, "error": err}
        except Exception as e:
            console.print(f"[bold red][-][/bold red] Exception during package installation for {package_name}: {e}")
            return {"success": False, "package": package_name, "version": resolved_version, "error": str(e)}

    def install_prepackaged_rules(self) -> bool:
        """Loads prebuilt detection rules into the Elastic Security Detection Engine."""
        console.print("[bold cyan][*][/bold cyan] Loading prepackaged Security Detection Rules (`POST /api/detection_engine/rules/prepackaged`)...")
        url = f"{self.kibana_url}/api/detection_engine/rules/prepackaged"

        try:
            resp = requests.post(url, headers=self.kbn_headers, json={}, verify=self.verify_ssl, timeout=120)
            if resp.status_code in (200, 201):
                data = resp.json()
                installed = data.get("rules_installed", 0)
                timelines = data.get("timelines_installed", 0)
                console.print(f"[bold green][+][/bold green] Prepackaged rules loaded: {installed} rules, {timelines} timelines")
                return True
            else:
                console.print(f"[yellow][!][/yellow] Prepackaged rules response ({resp.status_code}): {resp.text[:200]}")
                return False
        except Exception as e:
            console.print(f"[yellow][!][/yellow] Error loading prepackaged rules: {e}")
            return False

    def verify_installed_assets(self, package_names: List[str]) -> Dict[str, Dict[str, Any]]:
        """Verifies that index templates, ingest pipelines, and Kibana dashboards exist in the cluster."""
        results: Dict[str, Dict[str, Any]] = {}

        for pkg in package_names:
            pkg_targets = VERIFICATION_TARGETS.get(pkg)
            if not pkg_targets:
                continue

            results[pkg] = {
                "templates_found": 0,
                "templates_total": len(pkg_targets["index_templates"]),
                "pipelines_found": 0,
                "pipelines_total": len(pkg_targets["pipelines"]),
                "dashboards_found": 0,
                "data_streams": KEY_DATA_STREAMS.get(pkg, []),
                "all_ok": True,
            }

            # 1. Verify ES Index Templates
            if self.es_url:
                for tmpl in pkg_targets["index_templates"]:
                    url = f"{self.es_url}/_index_template/{tmpl}"
                    try:
                        r = requests.get(url, headers=self.es_headers, verify=self.verify_ssl, timeout=self.timeout)
                        if r.status_code == 200:
                            results[pkg]["templates_found"] += 1
                        else:
                            results[pkg]["all_ok"] = False
                    except Exception:
                        results[pkg]["all_ok"] = False

                # 2. Verify ES Ingest Pipelines
                for pipe in pkg_targets["pipelines"]:
                    url = f"{self.es_url}/_ingest/pipeline/{pipe}"
                    try:
                        r = requests.get(url, headers=self.es_headers, verify=self.verify_ssl, timeout=self.timeout)
                        if r.status_code == 200:
                            results[pkg]["pipelines_found"] += 1
                        else:
                            results[pkg]["all_ok"] = False
                    except Exception:
                        results[pkg]["all_ok"] = False

            # 3. Verify Kibana Dashboards
            d_prefix = pkg_targets["dashboard_prefix"]
            url = f"{self.kibana_url}/api/saved_objects/_find?type=dashboard&per_page=200"
            try:
                r = requests.get(url, headers=self.kbn_headers, verify=self.verify_ssl, timeout=self.timeout)
                if r.status_code == 200:
                    saved_objs = r.json().get("saved_objects", [])
                    matched = [
                        o for o in saved_objs
                        if o.get("id", "").startswith(d_prefix)
                        or pkg in o.get("id", "").lower()
                        or pkg in o.get("attributes", {}).get("title", "").lower()
                    ]
                    results[pkg]["dashboards_found"] = len(matched)
            except Exception:
                pass

        return results

    def export_offline_bundle(self, export_dir: str, package_names: List[str]) -> bool:
        """Exports index templates, pipelines, and saved objects for offline air-gapped stack rebuilds."""
        os.makedirs(export_dir, exist_ok=True)
        console.print(f"[bold cyan][*][/bold cyan] Exporting offline asset bundle to [bold]{export_dir}[/bold]...")

        manifest: Dict[str, Any] = {
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "kibana_url": self.kibana_url,
            "packages": {},
        }

        for pkg in package_names:
            pkg_info = self.get_package_info(pkg)
            if not pkg_info:
                continue

            ver = pkg_info.get("version") or pkg_info.get("latestVersion")
            manifest["packages"][pkg] = {
                "version": ver,
                "title": pkg_info.get("title"),
                "assets": [],
            }

            pkg_dir = os.path.join(export_dir, pkg)
            os.makedirs(pkg_dir, exist_ok=True)

            info_file = os.path.join(pkg_dir, "package_info.json")
            with open(info_file, "w", encoding="utf-8") as f:
                json.dump(pkg_info, f, indent=2)

            install_info = pkg_info.get("installationInfo", {})
            installed_es = install_info.get("installed_es", [])
            es_dir = os.path.join(pkg_dir, "elasticsearch")
            os.makedirs(es_dir, exist_ok=True)

            if self.es_url:
                for asset in installed_es:
                    a_type = asset.get("type")
                    a_id = asset.get("id")
                    endpoint_map = {
                        "index_template": f"_index_template/{a_id}",
                        "component_template": f"_component_template/{a_id}",
                        "ingest_pipeline": f"_ingest/pipeline/{a_id}",
                    }
                    if a_type in endpoint_map:
                        url = f"{self.es_url}/{endpoint_map[a_type]}"
                        try:
                            r = requests.get(url, headers=self.es_headers, verify=self.verify_ssl, timeout=self.timeout)
                            if r.status_code == 200:
                                out_file = os.path.join(es_dir, f"{a_type}_{a_id.replace('@', '_at_')}.json")
                                with open(out_file, "w", encoding="utf-8") as f:
                                    json.dump(r.json(), f, indent=2)
                        except Exception as e:
                            console.print(f"[yellow][!][/yellow] Failed to export {a_type} {a_id}: {e}")

            kbn_url = f"{self.kibana_url}/api/saved_objects/_export"
            try:
                r = requests.post(
                    kbn_url,
                    headers=self.kbn_headers,
                    json={"types": ["dashboard", "search", "visualization", "tag", "index-pattern"]},
                    verify=self.verify_ssl,
                    timeout=self.timeout,
                )
                if r.status_code == 200:
                    so_file = os.path.join(pkg_dir, "kibana_saved_objects.ndjson")
                    with open(so_file, "wb") as f:
                        f.write(r.content)
            except Exception as e:
                console.print(f"[yellow][!][/yellow] Failed to export saved objects for {pkg}: {e}")

        manifest_path = os.path.join(export_dir, "offline_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        console.print(f"[bold green][+][/bold green] Offline bundle successfully exported to [bold]{export_dir}[/bold]")
        return True


def parse_arguments() -> argparse.Namespace:
    """Configures and parses command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Automate integration asset installation (Windows, Elastic Defend, FortiGate, Palo Alto Firewall) for rebuilt Elastic Stacks.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--packages",
        nargs="+",
        default=["windows", "endpoint", "fortinet_fortigate", "panw"],
        help="List of packages to install/verify (options: windows, endpoint, fortinet_fortigate, panw)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=True,
        help="Force reinstallation of package assets even if already installed",
    )
    parser.add_argument(
        "--no-force",
        dest="force",
        action="store_false",
        help="Do not force reinstall if package is already installed",
    )
    parser.add_argument(
        "--wait-ready",
        type=int,
        default=120,
        help="Maximum seconds to wait for Kibana readiness before proceeding",
    )
    parser.add_argument(
        "--install-rules",
        action="store_true",
        default=False,
        help="Initialize prepackaged Security Detection Rules in Kibana",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        default=True,
        help="Verify installed templates, pipelines, and dashboards after installation",
    )
    parser.add_argument(
        "--no-verify",
        dest="verify",
        action="store_false",
        help="Skip post-installation asset verification",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        default=False,
        help="Only verify existing integration assets without installing anything",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Inspect packages and plan installation without executing modifying requests",
    )
    parser.add_argument(
        "--export-offline",
        type=str,
        default="",
        help="Directory path to export offline asset bundle for air-gapped stack rebuilds",
    )
    parser.add_argument(
        "--kibana-url",
        type=str,
        default="",
        help="Kibana base URL (overrides .env KIBANA_URL)",
    )
    parser.add_argument(
        "--es-url",
        type=str,
        default="",
        help="Elasticsearch base URL (overrides .env ES_URL)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default="",
        help="Kibana/Elasticsearch API Key (overrides .env)",
    )
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        default=False,
        help="Enforce strict SSL verification",
    )

    return parser.parse_args()


def display_verification_results(results: Dict[str, Dict[str, Any]]) -> None:
    """Renders a Rich table of verification results."""
    table = Table(title="Integration Assets Verification Report", title_style="bold cyan", border_style="dim")
    table.add_column("Integration", style="bold white", justify="left")
    table.add_column("Index Templates", justify="center")
    table.add_column("Ingest Pipelines", justify="center")
    table.add_column("Dashboards", justify="center")
    table.add_column("Key Data Streams", style="dim", justify="left")
    table.add_column("Status", justify="center")

    for pkg, data in results.items():
        tmpls = f"{data['templates_found']}/{data['templates_total']}"
        pipes = f"{data['pipelines_found']}/{data['pipelines_total']}"
        dashes = str(data["dashboards_found"])
        streams = "\n".join(data["data_streams"])
        status = "[bold green]HEALTHY[/bold green]" if data["all_ok"] else "[bold red]INCOMPLETE[/bold red]"
        table.add_row(pkg, tmpls, pipes, dashes, streams, status)

    console.print(table)


def main() -> None:
    args = parse_arguments()
    env = load_env()

    kibana_url = args.kibana_url or env.get("KIBANA_URL", "http://localhost:5601")
    es_url = args.es_url or env.get("ES_URL", "https://localhost:9200")
    api_key = args.api_key or env.get("KIBANA_API_KEY") or env.get("ES_API_KEY", "")

    if not api_key:
        console.print("[bold red][-][/bold red] API Key required. Set KIBANA_API_KEY in .env or provide --api-key.")
        sys.exit(1)

    console.print(
        Panel(
            f"[bold]Kibana URL:[/bold] {kibana_url}\n"
            f"[bold]Elasticsearch URL:[/bold] {es_url}\n"
            f"[bold]Target Packages:[/bold] {', '.join(args.packages)}\n"
            f"[bold]Mode:[/bold] {'VERIFY-ONLY' if args.verify_only else ('DRY-RUN' if args.dry_run else 'INSTALL & CONFIGURE')}",
            title="🛡️ Elastic Stack Rebuild Integration Asset Automator",
            border_style="cyan",
        )
    )

    installer = IntegrationAssetInstaller(
        kibana_url=kibana_url,
        api_key=api_key,
        es_url=es_url,
        verify_ssl=args.verify_ssl,
    )

    # 1. Wait for Kibana Readiness (unless verify-only without wait)
    if not args.verify_only:
        if not installer.wait_for_kibana_ready(max_wait_seconds=args.wait_ready):
            sys.exit(1)

    # 2. Export Offline Bundle if requested
    if args.export_offline:
        installer.export_offline_bundle(args.export_offline, args.packages)
        return

    # 3. Dry-Run Mode Inspection
    if args.dry_run:
        console.print("\n[bold yellow]=== DRY RUN INSPECTION ===[/bold yellow]")
        for pkg in args.packages:
            info = installer.get_package_info(pkg)
            if info:
                status = info.get("status", "unknown")
                ver = info.get("version") or info.get("latestVersion")
                console.print(f"  • [bold]{pkg}[/bold]: Version [cyan]{ver}[/cyan] | Current Status: [magenta]{status}[/magenta]")
            else:
                console.print(f"  • [bold]{pkg}[/bold]: Not found or unreachable in registry")
        return

    # 4. Verify-Only Mode
    if args.verify_only:
        console.print("\n[bold cyan]=== VERIFYING CURRENT INTEGRATION ASSETS ===[/bold cyan]")
        results = installer.verify_installed_assets(args.packages)
        display_verification_results(results)
        return

    # 5. Initialize Fleet
    if not installer.initialize_fleet():
        console.print("[bold red][-][/bold red] Fleet initialization failed. Aborting asset installation.")
        sys.exit(1)

    # 6. Install Each Integration Package
    installation_summary: List[Dict[str, Any]] = []
    for pkg in args.packages:
        res = installer.install_package(package_name=pkg, force=args.force)
        installation_summary.append(res)

    # 7. Optionally Load Prepackaged Detection Rules
    if args.install_rules:
        installer.install_prepackaged_rules()

    # 8. Verify Installed Assets
    if args.verify:
        console.print("\n[bold cyan]=== VERIFYING INSTALLED INTEGRATION ASSETS ===[/bold cyan]")
        results = installer.verify_installed_assets(args.packages)
        display_verification_results(results)

    console.print("\n[bold green]✓ Asset installation workflow completed successfully![/bold green]")


if __name__ == "__main__":
    main()
