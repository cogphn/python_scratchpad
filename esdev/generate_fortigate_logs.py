#!/usr/bin/env python3
"""Synthetic Fortinet FortiGate Firewall Log Generator for Detection Rule Testing.

Generates realistic timeseries data (90% baseline, 10% detection attack scenarios),
maintains persistent CSV entity catalogs, and writes to Elasticsearch data streams.
"""

import argparse
import datetime
import json
import os
import random
import sys
import time
from typing import Any, Dict, Generator, List, Optional, Tuple
import requests
import urllib3

from entity_manager import EntityManager
from scenarios import ScenarioEngine

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_env_defaults() -> Dict[str, str]:
    """Loads Elasticsearch and Kibana connection defaults from .env or .env_googledev."""
    config = {}
    for env_file in [".env_googledev", ".env"]:
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


def parse_arguments() -> argparse.Namespace:
    """Parses command line arguments."""
    env_defaults = load_env_defaults()
    default_es_url = os.environ.get("ES_URL", "https://localhost:9200")
    default_api_key = env_defaults.get("KIBANA_API_KEY", os.environ.get("ES_API_KEY", ""))

    parser = argparse.ArgumentParser(
        description="Synthetic Fortinet FortiGate Log Generator for Elastic Security Detection Testing",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--count", "-n",
        type=int,
        default=10000,
        help="Total number of events to generate"
    )
    parser.add_argument(
        "--backfill-days",
        type=float,
        default=3.0,
        help="Number of days in the past to start timeseries distribution"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2000,
        help="Number of events per Elasticsearch bulk commit"
    )
    parser.add_argument(
        "--threat-ratio",
        type=float,
        default=0.10,
        help="Proportion of security threat detection scenarios (e.g. 0.10 = 10%% threats, 90%% baseline)"
    )
    parser.add_argument(
        "--scenario",
        choices=["all", "baseline", "port_scan", "c2_beacon", "brute_force", "ips", "virus"],
        default="all",
        help="Filter generation to a specific scenario, or 'all' for mixed traffic"
    )
    parser.add_argument(
        "--allow-new-entities",
        action="store_true",
        default=False,
        help="Allow generating new entities and automatically appending them to CSV entity files"
    )
    parser.add_argument(
        "--mode",
        choices=["pipeline", "direct"],
        default="pipeline",
        help="Ingestion mode: 'pipeline' passes raw Syslog through logs-fortinet_fortigate.log-1.36.10; 'direct' writes pre-mapped ECS"
    )
    parser.add_argument(
        "--data-stream",
        default="logs-fortinet_fortigate.log-default",
        help="Target Elasticsearch data stream"
    )
    parser.add_argument(
        "--pipeline",
        default="logs-fortinet_fortigate.log-1.36.10",
        help="Ingest pipeline to use in pipeline mode"
    )
    parser.add_argument(
        "--entities-dir",
        default="data/entities",
        help="Directory containing persistent CSV entity catalogs"
    )
    parser.add_argument(
        "--es-url",
        default=default_es_url,
        help="Elasticsearch base URL"
    )
    parser.add_argument(
        "--api-key",
        default=default_api_key,
        help="Elasticsearch API Key for authentication"
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        default=True,
        help="Disable SSL certificate verification (broken/self-signed certs)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print sample events to stdout without sending to Elasticsearch"
    )

    return parser.parse_args()


class TimeseriesClock:
    """Manages progression of event timestamps across a time horizon."""

    def __init__(self, total_records: int, backfill_days: float):
        self.total_records = max(1, total_records)
        self.end_time = datetime.datetime.now(datetime.timezone.utc)
        self.start_time = self.end_time - datetime.timedelta(days=backfill_days)
        self.total_seconds = (self.end_time - self.start_time).total_seconds()
        self.current_index = 0

    def next_timestamp(self) -> datetime.datetime:
        """Returns the next chronological timestamp with diurnal variation and slight jitter."""
        progress = self.current_index / self.total_records
        base_seconds = progress * self.total_seconds
        # Add slight jitter (+/- 2 seconds)
        jitter = random.uniform(-2.0, 2.0)
        event_time = self.start_time + datetime.timedelta(seconds=max(0, base_seconds + jitter))
        self.current_index += 1
        return event_time


class FortigateDataGenerator:
    """Orchestrates entity management, scenario generation, and bulk indexing."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.entity_manager = EntityManager(
            entities_dir=args.entities_dir,
            allow_new_entities=args.allow_new_entities
        )
        self.scenario_engine = ScenarioEngine(self.entity_manager)
        self.clock = TimeseriesClock(args.count, args.backfill_days)

        self.scenario_counts: Dict[str, int] = {}
        self.session = requests.Session()
        self.session.verify = not args.insecure
        if args.api_key:
            self.session.headers.update({"Authorization": f"ApiKey {args.api_key}"})
        self.session.headers.update({"Content-Type": "application/x-ndjson"})

    def generate_events(self) -> Generator[Dict[str, Any], None, None]:
        """Yields synthetic FortiGate events."""
        for _ in range(self.args.count):
            ts = self.clock.next_timestamp()
            event = self.scenario_engine.next_event(
                dt=ts,
                threat_ratio=self.args.threat_ratio,
                scenario_filter=self.args.scenario
            )
            sc = event.get("scenario", "unknown")
            self.scenario_counts[sc] = self.scenario_counts.get(sc, 0) + 1
            yield event

    def run_dry_run(self) -> None:
        """Prints sample logs to stdout without sending to Elasticsearch."""
        sample_count = min(10, self.args.count)
        print(f"\n[DRY RUN] Showing {sample_count} sample events (Mode: {self.args.mode}):\n" + "=" * 80)
        generator = self.generate_events()
        for i in range(sample_count):
            event = next(generator)
            print(f"\n--- Sample {i+1} | Scenario: {event['scenario'].upper()} ---")
            if self.args.mode == "pipeline":
                print("Raw FortiOS Syslog String:")
                print(event["raw"])
            else:
                print("Pre-mapped ECS Document:")
                print(json.dumps(event["ecs"], indent=2))
        print("\n" + "=" * 80)
        print("[DRY RUN COMPLETE] No data written to Elasticsearch.")

    def run_ingest(self) -> None:
        """Indexes generated events into Elasticsearch using bulk batches."""
        target_url = f"{self.args.es_url.rstrip('/')}/{self.args.data_stream}/_bulk"
        if self.args.mode == "pipeline":
            target_url += f"?pipeline={self.args.pipeline}"
        else:
            # Direct mode writes pre-mapped ECS documents and bypasses the template default pipeline
            target_url += "?pipeline=_none"

        print(f"============================================================")
        print(f" Fortinet FortiGate Synthetic Log Generator")
        print(f"============================================================")
        print(f" Target ES URL:       {self.args.es_url}")
        print(f" Target Data Stream:  {self.args.data_stream}")
        print(f" Ingestion Mode:      {self.args.mode}")
        if self.args.mode == "pipeline":
            print(f" Ingest Pipeline:     {self.args.pipeline}")
        else:
            print(f" Pipeline Bypass:     ?pipeline=_none (Direct ECS mode)")
        print(f" Total Events:        {self.args.count:,}")
        print(f" Batch Size:          {self.args.batch_size:,}")
        print(f" Time Horizon:        {self.args.backfill_days} days")
        print(f" Scenario Filter:     {self.args.scenario}")
        print(f" Threat Ratio:        {self.args.threat_ratio * 100:.1f}% threats / {(1 - self.args.threat_ratio) * 100:.1f}% baseline")
        print(f" Entity Expansion:    {'ENABLED (New entities saved to CSV)' if self.args.allow_new_entities else 'DISABLED (Fixed CSV catalog)'}")
        print(f" Entity Directory:    {self.args.entities_dir}")
        print(f"============================================================\n")

        # Test ES connection before starting
        try:
            health_url = f"{self.args.es_url.rstrip('/')}/_cluster/health"
            r = self.session.get(health_url, timeout=10)
            if r.status_code != 200:
                print(f"[ERROR] Could not connect to Elasticsearch at {health_url}: HTTP {r.status_code} {r.text}")
                sys.exit(1)
            cluster_name = r.json().get("cluster_name", "unknown")
            cluster_status = r.json().get("status", "unknown")
            print(f"[OK] Connected to Elasticsearch cluster '{cluster_name}' (Status: {cluster_status})")
        except Exception as e:
            print(f"[ERROR] Failed to connect to Elasticsearch: {e}")
            sys.exit(1)

        start_time = time.time()
        total_indexed = 0
        total_errors = 0
        batch_lines: List[str] = []
        batch_count = 0

        action_line = json.dumps({"create": {}})

        for event in self.generate_events():
            # Validate schema compliance for essential fields
            fw_type = event.get("ecs", {}).get("fortinet", {}).get("firewall", {}).get("type")
            cat = event.get("ecs", {}).get("event", {}).get("category")
            if not fw_type or not cat:
                raise ValueError(
                    f"Schema violation in scenario {event.get('scenario')}: "
                    f"fortinet.firewall.type={fw_type}, event.category={cat}"
                )

            if self.args.mode == "pipeline":
                doc_line = json.dumps({"message": event["raw"]})
            else:
                doc_line = json.dumps(event["ecs"])

            batch_lines.append(action_line)
            batch_lines.append(doc_line)
            batch_count += 1

            if batch_count >= self.args.batch_size:
                indexed, errors = self._commit_batch(target_url, batch_lines)
                total_indexed += indexed
                total_errors += errors
                batch_lines = []
                batch_count = 0
                self._print_progress(total_indexed + total_errors, self.args.count, start_time)

        # Commit remaining events
        if batch_lines:
            indexed, errors = self._commit_batch(target_url, batch_lines)
            total_indexed += indexed
            total_errors += errors
            self._print_progress(total_indexed + total_errors, self.args.count, start_time)

        duration = max(0.001, time.time() - start_time)
        throughput = total_indexed / duration

        print("\n\n============================================================")
        print(" Ingestion Completed Successfully")
        print("============================================================")
        print(f" Successfully Indexed: {total_indexed:,} events")
        print(f" Failed / Errors:      {total_errors:,} events")
        print(f" Total Elapsed Time:   {duration:.2f} seconds")
        print(f" Throughput:           {throughput:.1f} events/sec")
        print("\n Scenarios Breakdown:")
        for sc, count in sorted(self.scenario_counts.items()):
            pct = (count / self.args.count) * 100
            print(f"  - {sc.ljust(15)}: {count:8,d} ({pct:5.1f}%)")
        print("\n Entities Catalog State:")
        print(f"  - Internal Hosts:    {len(self.entity_manager.internal_hosts):4,d} entries ({self.entity_manager.internal_hosts_file})")
        print(f"  - External Entities: {len(self.entity_manager.external_entities):4,d} entries ({self.entity_manager.external_entities_file})")
        print(f"  - Threat Entities:   {len(self.entity_manager.threat_entities):4,d} entries ({self.entity_manager.threat_entities_file})")
        print(f"  - Corporate Users:   {len(self.entity_manager.users):4,d} entries ({self.entity_manager.users_file})")
        print(f"  - Firewalls:         {len(self.entity_manager.firewalls):4,d} entries ({self.entity_manager.firewalls_file})")
        print("============================================================\n")

    def _commit_batch(self, url: str, batch_lines: List[str]) -> Tuple[int, int]:
        """Posts an NDJSON batch to Elasticsearch."""
        payload = "\n".join(batch_lines) + "\n"
        try:
            r = self.session.post(url, data=payload, timeout=60)
            if r.status_code not in (200, 201):
                print(f"\n[ERROR] Bulk POST returned HTTP {r.status_code}: {r.text[:200]}")
                return 0, len(batch_lines) // 2

            res = r.json()
            if not res.get("errors", False):
                return len(res.get("items", [])), 0

            # Count individual item failures
            indexed = 0
            errors = 0
            for item in res.get("items", []):
                status = item.get("create", {}).get("status", 500)
                if status in (200, 201):
                    indexed += 1
                else:
                    errors += 1
            return indexed, errors
        except Exception as e:
            print(f"\n[ERROR] Network error committing bulk batch: {e}")
            return 0, len(batch_lines) // 2

    @staticmethod
    def _print_progress(current: int, total: int, start_time: float) -> None:
        """Prints live progress and current speed."""
        pct = (current / total) * 100
        elapsed = max(0.001, time.time() - start_time)
        speed = current / elapsed
        sys.stdout.write(f"\r[Progress] Ingested {current:,} / {total:,} events ({pct:5.1f}%) | Speed: {speed:,.1f} events/sec")
        sys.stdout.flush()


def main():
    args = parse_arguments()
    generator = FortigateDataGenerator(args)

    if args.dry_run:
        generator.run_dry_run()
    else:
        generator.run_ingest()


if __name__ == "__main__":
    main()
