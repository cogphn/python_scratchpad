import csv
import os
import random
from typing import Any, Dict, List, Optional


class EntityManager:
    """Manages persistent entity catalogs in CSV files."""

    def __init__(self, entities_dir: str = "data/entities", allow_new_entities: bool = False):
        self.entities_dir = entities_dir
        self.allow_new_entities = allow_new_entities
        os.makedirs(entities_dir, exist_ok=True)

        self.internal_hosts_file = os.path.join(entities_dir, "internal_hosts.csv")
        self.external_entities_file = os.path.join(entities_dir, "external_entities.csv")
        self.threat_entities_file = os.path.join(entities_dir, "threat_entities.csv")
        self.users_file = os.path.join(entities_dir, "users.csv")
        self.firewalls_file = os.path.join(entities_dir, "firewalls.csv")

        self.internal_hosts: List[Dict[str, str]] = []
        self.external_entities: List[Dict[str, str]] = []
        self.threat_entities: List[Dict[str, str]] = []
        self.users: List[Dict[str, str]] = []
        self.firewalls: List[Dict[str, str]] = []

        self.load_or_seed()

    def load_or_seed(self) -> None:
        self.internal_hosts = self._load_or_seed_file(
            self.internal_hosts_file,
            self._get_default_internal_hosts(),
            ["ip", "hostname", "mac", "interface", "role", "user", "department"]
        )
        self.external_entities = self._load_or_seed_file(
            self.external_entities_file,
            self._get_default_external_entities(),
            ["ip", "domain", "service", "port", "proto", "asn", "country"]
        )
        self.threat_entities = self._load_or_seed_file(
            self.threat_entities_file,
            self._get_default_threat_entities(),
            ["ip", "domain", "threat_name", "attack_type", "severity", "cve_or_signature", "attackid"]
        )
        self.users = self._load_or_seed_file(
            self.users_file,
            self._get_default_users(),
            ["username", "role", "department", "workstation_ip", "vpn_allowed"]
        )
        self.firewalls = self._load_or_seed_file(
            self.firewalls_file,
            self._get_default_firewalls(),
            ["devname", "devid", "vd", "srcintf", "dstintf", "srcintfrole", "dstintfrole"]
        )

    def _load_or_seed_file(
        self,
        file_path: str,
        default_rows: List[Dict[str, Any]],
        fieldnames: List[str]
    ) -> List[Dict[str, str]]:
        """Reads rows from a CSV file, or creates and seeds it if missing or empty."""
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = [row for row in reader if any(row.values())]
                if rows:
                    return rows

        # First run or empty file: Seed defaults
        with open(file_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in default_rows:
                writer.writerow(row)
        return [{k: str(v) for k, v in row.items()} for row in default_rows]

    def append_entity(self, entity_type: str, row: Dict[str, Any]) -> bool:
        """Appends a newly discovered/generated entity to the corresponding CSV file."""
        if not self.allow_new_entities:
            return False

        mapping = {
            "internal_hosts": (self.internal_hosts, self.internal_hosts_file, ["ip", "hostname", "mac", "interface", "role", "user", "department"]),
            "external_entities": (self.external_entities, self.external_entities_file, ["ip", "domain", "service", "port", "proto", "asn", "country"]),
            "threat_entities": (self.threat_entities, self.threat_entities_file, ["ip", "domain", "threat_name", "attack_type", "severity", "cve_or_signature", "attackid"]),
            "users": (self.users, self.users_file, ["username", "role", "department", "workstation_ip", "vpn_allowed"]),
            "firewalls": (self.firewalls, self.firewalls_file, ["devname", "devid", "vd", "srcintf", "dstintf", "srcintfrole", "dstintfrole"]),
        }

        if entity_type not in mapping:
            return False

        entity_list, file_path, fieldnames = mapping[entity_type]
        str_row = {k: str(row.get(k, "")) for k in fieldnames}

        # Check for duplicates by key (ip or username or devname)
        key_field = "ip" if "ip" in fieldnames else ("username" if "username" in fieldnames else "devname")
        if any(item.get(key_field) == str_row.get(key_field) for item in entity_list):
            return False

        entity_list.append(str_row)
        with open(file_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow(str_row)
        return True

    def get_internal_host(self) -> Dict[str, str]:
        """Returns an internal host. Generates and persists a new one only if allow_new_entities is True."""
        if self.allow_new_entities and random.random() < 0.05:
            subnet = random.choice([10, 20, 30, 40, 50])
            host_num = random.randint(100, 254)
            new_ip = f"10.10.{subnet}.{host_num}"
            hostname = f"WS-CORP-{subnet}-{host_num}"
            mac = f"00:0c:29:{random.randint(10,99)}:{random.randint(10,99)}:{random.randint(10,99)}"
            dept = random.choice(["engineering", "sales", "finance", "hr", "operations"])
            new_entity = {
                "ip": new_ip,
                "hostname": hostname,
                "mac": mac,
                "interface": "port1" if subnet < 30 else "port2",
                "role": "workstation" if subnet != 20 else "server",
                "user": f"user_{subnet}_{host_num}",
                "department": dept,
            }
            if self.append_entity("internal_hosts", new_entity):
                return new_entity
        return random.choice(self.internal_hosts)

    def get_external_entity(self) -> Dict[str, str]:
        """Returns an external entity."""
        if self.allow_new_entities and random.random() < 0.05:
            octet1 = random.choice([52, 104, 142, 151, 198, 204])
            octet2 = random.randint(10, 200)
            octet3 = random.randint(1, 254)
            octet4 = random.randint(1, 254)
            new_ip = f"{octet1}.{octet2}.{octet3}.{octet4}"
            domain = f"api-node-{octet2}.cloudservice.net"
            new_entity = {
                "ip": new_ip,
                "domain": domain,
                "service": "HTTPS",
                "port": "443",
                "proto": "tcp",
                "asn": str(random.choice([15169, 16509, 13335, 8075])),
                "country": random.choice(["US", "IE", "DE", "GB", "SG"]),
            }
            if self.append_entity("external_entities", new_entity):
                return new_entity
        return random.choice(self.external_entities)

    def get_threat_entity(self) -> Dict[str, str]:
        """Returns a threat entity."""
        return random.choice(self.threat_entities)

    def get_user(self) -> Dict[str, str]:
        """Returns a corporate user."""
        return random.choice(self.users)

    def get_firewall(self) -> Dict[str, str]:
        """Returns a firewall configuration."""
        return random.choice(self.firewalls)

    # --- DEFAULT SEED CATALOGS ---

    @staticmethod
    def _get_default_internal_hosts() -> List[Dict[str, Any]]:
        return [
            {"ip": "10.10.10.15", "hostname": "WS-EXEC-01", "mac": "00:0c:29:4f:8e:11", "interface": "port1", "role": "workstation", "user": "ceo_john", "department": "executive"},
            {"ip": "10.10.10.42", "hostname": "WS-DEV-12", "mac": "00:0c:29:4f:8e:22", "interface": "port1", "role": "workstation", "user": "dev_alice", "department": "engineering"},
            {"ip": "10.10.10.88", "hostname": "WS-SALES-05", "mac": "00:0c:29:4f:8e:33", "interface": "port1", "role": "workstation", "user": "bob_sales", "department": "sales"},
            {"ip": "10.10.10.95", "hostname": "WS-FIN-03", "mac": "00:0c:29:4f:8e:44", "interface": "port1", "role": "workstation", "user": "fin_carol", "department": "finance"},
            {"ip": "10.10.20.10", "hostname": "SRV-DC-01", "mac": "00:0c:29:4f:8e:55", "interface": "port2", "role": "server", "user": "admin_root", "department": "it_infrastructure"},
            {"ip": "10.10.20.25", "hostname": "SRV-FILE-01", "mac": "00:0c:29:4f:8e:66", "interface": "port2", "role": "server", "user": "svc_storage", "department": "it_infrastructure"},
            {"ip": "10.10.20.50", "hostname": "SRV-APP-PROD", "mac": "00:0c:29:4f:8e:77", "interface": "port2", "role": "server", "user": "svc_app", "department": "production"},
            {"ip": "10.10.20.80", "hostname": "SRV-DB-MAIN", "mac": "00:0c:29:4f:8e:88", "interface": "port2", "role": "server", "user": "svc_db", "department": "production"},
            {"ip": "10.10.30.100", "hostname": "GUEST-PHONE-01", "mac": "00:0c:29:4f:8e:99", "interface": "port3", "role": "mobile", "user": "guest_user", "department": "contractor"},
            {"ip": "10.10.30.105", "hostname": "IOT-PRINTER-01", "mac": "00:0c:29:4f:8e:aa", "interface": "port3", "role": "iot", "user": "printer_service", "department": "facilities"},
        ]

    @staticmethod
    def _get_default_external_entities() -> List[Dict[str, Any]]:
        return [
            {"ip": "8.8.8.8", "domain": "dns.google", "service": "DNS", "port": 53, "proto": "udp", "asn": 15169, "country": "US"},
            {"ip": "1.1.1.1", "domain": "one.one.one.one", "service": "DNS", "port": 53, "proto": "udp", "asn": 13335, "country": "US"},
            {"ip": "142.250.190.46", "domain": "www.google.com", "service": "HTTPS", "port": 443, "proto": "tcp", "asn": 15169, "country": "US"},
            {"ip": "52.96.166.130", "domain": "outlook.office365.com", "service": "HTTPS", "port": 443, "proto": "tcp", "asn": 8075, "country": "US"},
            {"ip": "151.101.65.140", "domain": "reddit.com", "service": "HTTPS", "port": 443, "proto": "tcp", "asn": 13335, "country": "US"},
            {"ip": "140.82.121.4", "domain": "github.com", "service": "HTTPS", "port": 443, "proto": "tcp", "asn": 36459, "country": "US"},
            {"ip": "104.16.132.229", "domain": "cloudflare.com", "service": "HTTPS", "port": 443, "proto": "tcp", "asn": 13335, "country": "US"},
            {"ip": "13.107.42.16", "domain": "teams.microsoft.com", "service": "HTTPS", "port": 443, "proto": "tcp", "asn": 8075, "country": "US"},
            {"ip": "17.253.144.10", "domain": "apple.com", "service": "HTTPS", "port": 443, "proto": "tcp", "asn": 714, "country": "US"},
            {"ip": "199.232.69.194", "domain": "pypi.org", "service": "HTTPS", "port": 443, "proto": "tcp", "asn": 54113, "country": "US"},
        ]

    @staticmethod
    def _get_default_threat_entities() -> List[Dict[str, Any]]:
        return [
            {
                "ip": "185.220.101.5",
                "domain": "tor-exit.darknet.org",
                "threat_name": "Tor Exit Node",
                "attack_type": "recon",
                "severity": "medium",
                "cve_or_signature": "TOR-EXIT-NODE-SCAN",
                "attackid": 10001,
            },
            {
                "ip": "194.26.29.112",
                "domain": "c2-command.darkoperator.cc",
                "threat_name": "Cobalt Strike C2",
                "attack_type": "c2_beacon",
                "severity": "critical",
                "cve_or_signature": "COBALT-STRIKE-BEACON",
                "attackid": 20045,
            },
            {
                "ip": "45.146.164.110",
                "domain": "exploit-kit.malicious.net",
                "threat_name": "Log4j RCE Remote Execution",
                "attack_type": "ips",
                "severity": "critical",
                "cve_or_signature": "CVE-2021-44228",
                "attackid": 30012,
            },
            {
                "ip": "198.51.100.99",
                "domain": "badlogin.attacker.net",
                "threat_name": "SSH & WebUI Brute Force",
                "attack_type": "brute_force",
                "severity": "high",
                "cve_or_signature": "AUTH-BRUTE-FORCE-BURST",
                "attackid": 40001,
            },
            {
                "ip": "203.0.113.88",
                "domain": "ransomware-cdn.evil.xyz",
                "threat_name": "LockBit Dropper Payload",
                "attack_type": "virus",
                "severity": "critical",
                "cve_or_signature": "W32/LockBit.Gen!tr",
                "attackid": 50022,
            },
            {
                "ip": "91.240.118.172",
                "domain": "scanner-probe.shodan-like.org",
                "threat_name": "Mass Internet Port Scanner",
                "attack_type": "port_scan",
                "severity": "medium",
                "cve_or_signature": "SCAN-TCP-SYN-BURST",
                "attackid": 60033,
            },
            {
                "ip": "185.191.171.12",
                "domain": "dns-exfil.tunneling-bot.com",
                "threat_name": "DNS Data Exfiltration Tunnel",
                "attack_type": "dns_tunnel",
                "severity": "high",
                "cve_or_signature": "DNS-TUNNELING-ANOMALY",
                "attackid": 70044,
            },
        ]

    @staticmethod
    def _get_default_users() -> List[Dict[str, Any]]:
        return [
            {"username": "jdoe", "role": "admin", "department": "it_security", "workstation_ip": "10.10.10.15", "vpn_allowed": "true"},
            {"username": "alice_dev", "role": "developer", "department": "engineering", "workstation_ip": "10.10.10.42", "vpn_allowed": "true"},
            {"username": "bob_sales", "role": "sales_rep", "department": "sales", "workstation_ip": "10.10.10.88", "vpn_allowed": "true"},
            {"username": "fin_carol", "role": "accountant", "department": "finance", "workstation_ip": "10.10.10.95", "vpn_allowed": "true"},
            {"username": "admin_root", "role": "sysadmin", "department": "it_infrastructure", "workstation_ip": "10.10.20.10", "vpn_allowed": "true"},
            {"username": "contractor_mike", "role": "consultant", "department": "contractor", "workstation_ip": "10.10.30.100", "vpn_allowed": "false"},
            {"username": "attacker_probe", "role": "unknown", "department": "external", "workstation_ip": "198.51.100.99", "vpn_allowed": "false"},
        ]

    @staticmethod
    def _get_default_firewalls() -> List[Dict[str, Any]]:
        return [
            {
                "devname": "FW-EDGE-01",
                "devid": "FGT60E4Q17001234",
                "vd": "root",
                "srcintf": "port1",
                "dstintf": "port2",
                "srcintfrole": "lan",
                "dstintfrole": "wan"
            },
            {
                "devname": "FW-CORE-02",
                "devid": "FGT100E5Q19005678",
                "vd": "root",
                "srcintf": "internal",
                "dstintf": "wan1",
                "srcintfrole": "lan",
                "dstintfrole": "wan"
            }
        ]
