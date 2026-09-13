import datetime
import random
import uuid
from typing import Any, Dict, List, Optional, Tuple
from entity_manager import EntityManager


class ScenarioEngine:
    """Generates FortiGate telemetry scenarios for baseline and attack detection."""

    def __init__(self, entity_manager: EntityManager):
        self.em = entity_manager
        self.session_counter = random.randint(100000, 999999)
        self.log_counter = random.randint(1000000000, 9999999999)

    def _next_session_id(self) -> int:
        self.session_counter += 1
        return self.session_counter

    def _next_log_id(self) -> str:
        self.log_counter += 1
        return str(self.log_counter)

    @staticmethod
    def _format_timestamp(dt: datetime.datetime) -> Tuple[str, str, int]:
        """Returns (date_str, time_str, epoch_seconds)."""
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H:%M:%S")
        epoch_sec = int(dt.timestamp())
        return date_str, time_str, epoch_sec

    # =========================================================================
    # SCENARIO 1: Baseline Network Traffic (90% of Volume)
    # =========================================================================

    def generate_baseline(self, dt: datetime.datetime) -> Dict[str, Any]:
        """Generates realistic normal corporate network traffic (Web, DNS, Cloud APIs)."""
        date_str, time_str, epoch_sec = self._format_timestamp(dt)
        internal = self.em.get_internal_host()
        external = self.em.get_external_entity()
        firewall = self.em.get_firewall()
        session_id = self._next_session_id()
        log_id = self._next_log_id()

        service = external.get("service", "HTTPS")
        port = int(external.get("port", 443))
        proto = 17 if external.get("proto") == "udp" else 6
        proto_name = "udp" if proto == 17 else "tcp"

        action = random.choices(["accept", "close", "timeout"], weights=[60, 35, 5])[0]
        duration = random.randint(1, 180) if action != "timeout" else 300

        # Correlated byte counts based on service
        if service == "DNS":
            sent_byte = random.randint(60, 120)
            rcvd_byte = random.randint(80, 512)
            sent_pkt = 1
            rcvd_pkt = 1
            app = "DNS"
            appcat = "Network.Service"
        elif service == "HTTPS":
            sent_byte = random.randint(1000, 25000)
            rcvd_byte = random.randint(5000, 850000)
            sent_pkt = max(5, sent_byte // 1460)
            rcvd_pkt = max(8, rcvd_byte // 1460)
            app = random.choice(["HTTPS.BROWSER", "Google.Services", "Office365.Portal", "GitHub", "Cloudflare.CDN"])
            appcat = "General.Interest"
        else:
            sent_byte = random.randint(500, 10000)
            rcvd_byte = random.randint(500, 50000)
            sent_pkt = max(3, sent_byte // 1000)
            rcvd_pkt = max(4, rcvd_byte // 1000)
            app = service
            appcat = "Web.Client"

        src_port = random.randint(1025, 65534)
        policy_id = random.choice([1, 2, 5, 10, 20])

        raw_syslog = (
            f'<189>date={date_str} time={time_str} devname="{firewall["devname"]}" '
            f'devid="{firewall["devid"]}" eventtime={epoch_sec} '
            f'logid="{log_id}" type="traffic" subtype="forward" level="notice" vd="{firewall["vd"]}" '
            f'srcip={internal["ip"]} srcport={src_port} srcintf="{firewall["srcintf"]}" srcintfrole="{firewall["srcintfrole"]}" '
            f'dstip={external["ip"]} dstport={port} dstintf="{firewall["dstintf"]}" dstintfrole="{firewall["dstintfrole"]}" '
            f'srccountry="Reserved" dstcountry="{external.get("country", "US")}" '
            f'sessionid={session_id} proto={proto} action="{action}" policyid={policy_id} '
            f'service="{service}" trandisp="snat" transip=198.51.100.1 transport={src_port} '
            f'duration={duration} sentbyte={sent_byte} rcvdbyte={rcvd_byte} '
            f'sentpkt={sent_pkt} rcvdpkt={rcvd_pkt} appcat="{appcat}" app="{app}" '
            f'crscore=0 craction=0'
        )

        ecs_doc = {
            "@timestamp": dt.isoformat(),
            "data_stream": {
                "type": "logs",
                "dataset": "fortinet_fortigate.log",
                "namespace": "default"
            },
            "message": raw_syslog,
            "observer": {
                "vendor": "Fortinet",
                "product": "FortiGate",
                "type": "firewall",
                "name": firewall["devname"],
                "serial_number": firewall["devid"],
                "ingress": {"interface": {"name": firewall["srcintf"]}},
                "egress": {"interface": {"name": firewall["dstintf"]}}
            },
            "event": {
                "kind": "event",
                "category": ["network"],
                "type": ["connection", "allowed" if action != "timeout" else "denied"],
                "action": action,
                "duration": duration * 1000000000,
                "code": log_id,
                "outcome": "success" if action != "timeout" else "failure",
                "dataset": "fortinet_fortigate.log",
                "module": "fortinet_fortigate",
                "original": raw_syslog
            },
            "network": {
                "transport": proto_name,
                "iana_number": str(proto),
                "direction": "outbound",
                "bytes": sent_byte + rcvd_byte,
                "packets": sent_pkt + rcvd_pkt,
                "application": app
            },
            "source": {
                "ip": internal["ip"],
                "port": src_port,
                "bytes": sent_byte,
                "packets": sent_pkt,
                "address": internal["ip"]
            },
            "destination": {
                "ip": external["ip"],
                "port": port,
                "bytes": rcvd_byte,
                "packets": rcvd_pkt,
                "address": external.get("domain", external["ip"]),
                "domain": external.get("domain", "")
            },
            "rule": {
                "id": str(policy_id),
                "category": appcat
            },
            "fortinet": {
                "firewall": {
                    "type": "traffic",
                    "subtype": "forward",
                    "action": action,
                    "sessionid": str(session_id),
                    "crscore": "0",
                    "craction": "0",
                    "vd": firewall["vd"]
                }
            },
            "related": {
                "ip": [internal["ip"], external["ip"]],
                "hosts": [external.get("domain")] if external.get("domain") else []
            }
        }

        return {"raw": raw_syslog, "ecs": ecs_doc, "scenario": "baseline"}

    # =========================================================================
    # SCENARIO 2: Port Scan / Reconnaissance Attack (Security Detection)
    # =========================================================================

    def generate_port_scan(self, dt: datetime.datetime) -> Dict[str, Any]:
        """Generates a probe packet indicating an inbound or lateral port scan."""
        date_str, time_str, epoch_sec = self._format_timestamp(dt)
        threat = self.em.get_threat_entity()
        target = self.em.get_internal_host()
        firewall = self.em.get_firewall()
        session_id = self._next_session_id()
        log_id = self._next_log_id()

        # Probing well-known scan ports
        scanned_port = random.choice([21, 22, 23, 25, 80, 443, 445, 1433, 3306, 3389, 8080, 8443, 9200])
        src_port = random.randint(40000, 65000)

        raw_syslog = (
            f'<189>date={date_str} time={time_str} devname="{firewall["devname"]}" '
            f'devid="{firewall["devid"]}" eventtime={epoch_sec} '
            f'logid="{log_id}" type="traffic" subtype="forward" level="warning" vd="{firewall["vd"]}" '
            f'srcip={threat["ip"]} srcport={src_port} srcintf="{firewall["dstintf"]}" srcintfrole="wan" '
            f'dstip={target["ip"]} dstport={scanned_port} dstintf="{firewall["srcintf"]}" dstintfrole="lan" '
            f'sessionid={session_id} proto=6 action="deny" policyid=0 '
            f'service="tcp/{scanned_port}" duration=0 sentbyte=40 rcvdbyte=0 sentpkt=1 rcvdpkt=0 '
            f'crscore=30 craction=131072 crlevel="high" msg="Connection denied by policy 0 (Default Drop)"'
        )

        ecs_doc = {
            "@timestamp": dt.isoformat(),
            "data_stream": {
                "type": "logs",
                "dataset": "fortinet_fortigate.log",
                "namespace": "default"
            },
            "message": raw_syslog,
            "observer": {
                "vendor": "Fortinet",
                "product": "FortiGate",
                "type": "firewall",
                "name": firewall["devname"],
                "serial_number": firewall["devid"]
            },
            "event": {
                "kind": "event",
                "category": ["network"],
                "type": ["connection", "denied"],
                "action": "deny",
                "code": log_id,
                "outcome": "failure",
                "dataset": "fortinet_fortigate.log",
                "module": "fortinet_fortigate",
                "original": raw_syslog
            },
            "network": {
                "transport": "tcp",
                "direction": "inbound",
                "bytes": 40,
                "packets": 1
            },
            "source": {
                "ip": threat["ip"],
                "port": src_port,
                "bytes": 40,
                "packets": 1,
                "address": threat["ip"]
            },
            "destination": {
                "ip": target["ip"],
                "port": scanned_port,
                "bytes": 0,
                "packets": 0,
                "address": target["ip"]
            },
            "rule": {
                "id": "0",
                "name": "Default-Drop"
            },
            "fortinet": {
                "firewall": {
                    "type": "traffic",
                    "subtype": "forward",
                    "sessionid": str(session_id),
                    "crscore": "30",
                    "crlevel": "high",
                    "action": "deny",
                    "vd": firewall["vd"]
                }
            },
            "related": {
                "ip": [threat["ip"], target["ip"]]
            }
        }

        return {"raw": raw_syslog, "ecs": ecs_doc, "scenario": "port_scan"}

    # =========================================================================
    # SCENARIO 3: C2 Beaconing Activity (Security Detection)
    # =========================================================================

    def generate_c2_beacon(self, dt: datetime.datetime) -> Dict[str, Any]:
        """Generates periodic outbound telemetry to a Command-and-Control node."""
        date_str, time_str, epoch_sec = self._format_timestamp(dt)
        c2_threat = [t for t in self.em.threat_entities if t.get("attack_type") == "c2_beacon"]
        threat = c2_threat[0] if c2_threat else self.em.get_threat_entity()
        internal = self.em.get_internal_host()
        firewall = self.em.get_firewall()
        session_id = self._next_session_id()
        log_id = self._next_log_id()

        src_port = random.randint(49152, 65535)
        dst_port = 443
        sent_byte = random.randint(128, 256)
        rcvd_byte = random.randint(256, 512)

        raw_syslog = (
            f'<189>date={date_str} time={time_str} devname="{firewall["devname"]}" '
            f'devid="{firewall["devid"]}" eventtime={epoch_sec} '
            f'logid="{log_id}" type="traffic" subtype="forward" level="notice" vd="{firewall["vd"]}" '
            f'srcip={internal["ip"]} srcport={src_port} srcintf="{firewall["srcintf"]}" srcintfrole="lan" '
            f'dstip={threat["ip"]} dstport={dst_port} dstintf="{firewall["dstintf"]}" dstintfrole="wan" '
            f'sessionid={session_id} proto=6 action="close" policyid=2 '
            f'service="HTTPS" duration=2 sentbyte={sent_byte} rcvdbyte={rcvd_byte} sentpkt=4 rcvdpkt=4 '
            f'app="HTTPS" appcat="General.Interest" crscore=40 crlevel="high" '
            f'craction=0 dstname="{threat.get("domain", "")}"'
        )

        ecs_doc = {
            "@timestamp": dt.isoformat(),
            "data_stream": {
                "type": "logs",
                "dataset": "fortinet_fortigate.log",
                "namespace": "default"
            },
            "message": raw_syslog,
            "observer": {
                "vendor": "Fortinet",
                "product": "FortiGate",
                "type": "firewall",
                "name": firewall["devname"],
                "serial_number": firewall["devid"]
            },
            "event": {
                "kind": "event",
                "category": ["network"],
                "type": ["connection", "allowed"],
                "action": "close",
                "code": log_id,
                "outcome": "success",
                "dataset": "fortinet_fortigate.log",
                "module": "fortinet_fortigate",
                "original": raw_syslog
            },
            "network": {
                "transport": "tcp",
                "direction": "outbound",
                "bytes": sent_byte + rcvd_byte,
                "packets": 8,
                "application": "HTTPS"
            },
            "source": {
                "ip": internal["ip"],
                "port": src_port,
                "bytes": sent_byte,
                "packets": 4,
                "address": internal["ip"]
            },
            "destination": {
                "ip": threat["ip"],
                "port": dst_port,
                "bytes": rcvd_byte,
                "packets": 4,
                "address": threat.get("domain", threat["ip"]),
                "domain": threat.get("domain", "")
            },
            "rule": {
                "id": "2",
                "name": "Outbound-Web"
            },
            "threat": {
                "indicator": {
                    "ip": threat["ip"],
                    "name": threat.get("threat_name", "C2 Beacon")
                }
            },
            "fortinet": {
                "firewall": {
                    "type": "traffic",
                    "subtype": "forward",
                    "sessionid": str(session_id),
                    "crscore": "40",
                    "crlevel": "high",
                    "action": "close",
                    "vd": firewall["vd"]
                }
            },
            "related": {
                "ip": [internal["ip"], threat["ip"]],
                "hosts": [threat.get("domain")] if threat.get("domain") else []
            }
        }

        return {"raw": raw_syslog, "ecs": ecs_doc, "scenario": "c2_beacon"}

    # =========================================================================
    # SCENARIO 4: Authentication Brute Force (Security Detection)
    # =========================================================================

    def generate_login_attempt(self, dt: datetime.datetime, is_success: bool = False) -> Dict[str, Any]:
        """Generates authentication/login event (SSH/WebUI admin login or SSL-VPN auth)."""
        date_str, time_str, epoch_sec = self._format_timestamp(dt)
        user = self.em.get_user()
        firewall = self.em.get_firewall()
        log_id = self._next_log_id()

        # Failed attempts often come from external threat IPs; success from user workstation
        if not is_success:
            attacker_ips = [t["ip"] for t in self.em.threat_entities if t.get("attack_type") == "brute_force"]
            src_ip = attacker_ips[0] if attacker_ips else "198.51.100.99"
            status = "failed"
            action = "login"
            level = "warning"
            ui = "ssh"
            # Standard FortiOS admin login failed format matching Elastic login dissect pattern
            msg = f"Administrator {user['username']} login failed from ssh({src_ip}) because of invalid password"
        else:
            src_ip = user.get("workstation_ip", "10.10.10.15")
            status = "success"
            action = "login"
            level = "information"
            ui = "https"
            # Standard FortiOS admin logged in format matching Elastic login grok pattern
            msg = f"Administrator {user['username']} logged in successfully from https({src_ip})"

        raw_syslog = (
            f'<190>date={date_str} time={time_str} devname="{firewall["devname"]}" '
            f'devid="{firewall["devid"]}" eventtime={epoch_sec} logid="{log_id}" '
            f'type="event" subtype="system" level="{level}" vd="{firewall["vd"]}" '
            f'logdesc="Admin login {status}" action="{action}" status="{status}" '
            f'user="{user["username"]}" ui="{ui}" method="password" srcip={src_ip} '
            f'msg="{msg}"'
        )

        ecs_doc = {
            "@timestamp": dt.isoformat(),
            "data_stream": {
                "type": "logs",
                "dataset": "fortinet_fortigate.log",
                "namespace": "default"
            },
            "message": raw_syslog,
            "observer": {
                "vendor": "Fortinet",
                "product": "FortiGate",
                "type": "firewall",
                "name": firewall["devname"],
                "serial_number": firewall["devid"]
            },
            "event": {
                "kind": "event",
                "category": ["authentication"],
                "type": ["start", "info"],
                "action": "login",
                "code": log_id,
                "outcome": "success" if is_success else "failure",
                "dataset": "fortinet_fortigate.log",
                "module": "fortinet_fortigate",
                "original": raw_syslog
            },
            "source": {
                "ip": src_ip,
                "address": src_ip
            },
            "user": {
                "name": user["username"],
                "roles": [user.get("role", "user")]
            },
            "fortinet": {
                "firewall": {
                    "type": "event",
                    "subtype": "system",
                    "action": "login",
                    "status": status,
                    "msg": msg,
                    "ui": ui,
                    "vd": firewall["vd"]
                }
            },
            "related": {
                "ip": [src_ip],
                "user": [user["username"]]
            }
        }

        return {"raw": raw_syslog, "ecs": ecs_doc, "scenario": "brute_force"}

    # =========================================================================
    # SCENARIO 5: UTM IPS Exploit / Signature Detection (Security Detection)
    # =========================================================================

    def generate_utm_ips(self, dt: datetime.datetime) -> Dict[str, Any]:
        """Generates an Intrusion Prevention System (IPS) threat alert."""
        date_str, time_str, epoch_sec = self._format_timestamp(dt)
        ips_threats = [t for t in self.em.threat_entities if t.get("attack_type") == "ips"]
        threat = ips_threats[0] if ips_threats else self.em.get_threat_entity()
        target = self.em.get_internal_host()
        firewall = self.em.get_firewall()
        session_id = self._next_session_id()
        log_id = self._next_log_id()

        attack_name = threat.get("threat_name", "Apache.Log4j.JNDI.Remote.Code.Execution")
        attack_id = threat.get("attackid", "30012")
        cve = threat.get("cve_or_signature", "CVE-2021-44228")

        raw_syslog = (
            f'<187>date={date_str} time={time_str} devname="{firewall["devname"]}" '
            f'devid="{firewall["devid"]}" eventtime={epoch_sec} logid="{log_id}" '
            f'type="utm" subtype="ips" eventtype="signature" level="critical" vd="{firewall["vd"]}" '
            f'severity="critical" srcip={threat["ip"]} srccountry="Russian Federation" '
            f'dstip={target["ip"]} srcintf="{firewall["dstintf"]}" srcintfrole="wan" '
            f'dstintf="{firewall["srcintf"]}" dstintfrole="lan" sessionid={session_id} '
            f'action="dropped" proto=6 service="HTTP" attack="{attack_name}" attackid={attack_id} '
            f'direction="incoming" policyid=1 ref="http://www.fortinet.com/ids/VID{attack_id}" '
            f'incidentserialno={random.randint(10000000, 99999999)} msg="ips: {attack_name} ({cve})"'
        )

        ecs_doc = {
            "@timestamp": dt.isoformat(),
            "data_stream": {
                "type": "logs",
                "dataset": "fortinet_fortigate.log",
                "namespace": "default"
            },
            "message": raw_syslog,
            "observer": {
                "vendor": "Fortinet",
                "product": "FortiGate",
                "type": "firewall",
                "name": firewall["devname"],
                "serial_number": firewall["devid"]
            },
            "event": {
                "kind": "alert",
                "category": ["network", "intrusion_detection"],
                "type": ["denied", "indicator"],
                "action": "dropped",
                "code": log_id,
                "outcome": "failure",
                "dataset": "fortinet_fortigate.log",
                "module": "fortinet_fortigate",
                "original": raw_syslog
            },
            "network": {
                "transport": "tcp",
                "direction": "inbound",
                "application": "HTTP"
            },
            "source": {
                "ip": threat["ip"],
                "address": threat["ip"]
            },
            "destination": {
                "ip": target["ip"],
                "address": target["ip"]
            },
            "rule": {
                "id": str(attack_id),
                "name": attack_name,
                "reference": f"http://www.fortinet.com/ids/VID{attack_id}"
            },
            "vulnerability": {
                "id": cve
            },
            "fortinet": {
                "firewall": {
                    "type": "utm",
                    "subtype": "ips",
                    "attack": attack_name,
                    "attackid": str(attack_id),
                    "action": "dropped",
                    "severity": "critical",
                    "vd": firewall["vd"]
                }
            },
            "related": {
                "ip": [threat["ip"], target["ip"]]
            }
        }

        return {"raw": raw_syslog, "ecs": ecs_doc, "scenario": "ips"}

    # =========================================================================
    # SCENARIO 6: UTM Antivirus / Malware Transfer (Security Detection)
    # =========================================================================

    def generate_utm_virus(self, dt: datetime.datetime) -> Dict[str, Any]:
        """Generates an Antivirus infected file download detection event."""
        date_str, time_str, epoch_sec = self._format_timestamp(dt)
        virus_threats = [t for t in self.em.threat_entities if t.get("attack_type") == "virus"]
        threat = virus_threats[0] if virus_threats else self.em.get_threat_entity()
        internal = self.em.get_internal_host()
        firewall = self.em.get_firewall()
        session_id = self._next_session_id()
        log_id = self._next_log_id()

        malware_name = threat.get("threat_name", "W32/LockBit.Gen!tr")
        file_name = "invoice_payment_urgent.exe"

        raw_syslog = (
            f'<187>date={date_str} time={time_str} devname="{firewall["devname"]}" '
            f'devid="{firewall["devid"]}" eventtime={epoch_sec} logid="{log_id}" '
            f'type="utm" subtype="virus" eventtype="infected" level="critical" vd="{firewall["vd"]}" '
            f'srcip={threat["ip"]} dstip={internal["ip"]} srcintf="{firewall["dstintf"]}" dstintf="{firewall["srcintf"]}" '
            f'sessionid={session_id} proto=6 action="blocked" policyid=1 '
            f'service="HTTP" virus="{malware_name}" file="{file_name}" '
            f'url="http://{threat.get("domain", threat["ip"])}/payloads/{file_name}" '
            f'direction="incoming" msg="File {file_name} infected with {malware_name} blocked."'
        )

        ecs_doc = {
            "@timestamp": dt.isoformat(),
            "data_stream": {
                "type": "logs",
                "dataset": "fortinet_fortigate.log",
                "namespace": "default"
            },
            "message": raw_syslog,
            "observer": {
                "vendor": "Fortinet",
                "product": "FortiGate",
                "type": "firewall",
                "name": firewall["devname"],
                "serial_number": firewall["devid"]
            },
            "event": {
                "kind": "alert",
                "category": ["network", "malware", "file"],
                "type": ["denied", "indicator"],
                "action": "blocked",
                "code": log_id,
                "outcome": "failure",
                "dataset": "fortinet_fortigate.log",
                "module": "fortinet_fortigate",
                "original": raw_syslog
            },
            "file": {
                "name": file_name,
                "extension": "exe"
            },
            "threat": {
                "indicator": {
                    "name": malware_name,
                    "type": "file"
                }
            },
            "source": {
                "ip": threat["ip"],
                "address": threat["ip"]
            },
            "destination": {
                "ip": internal["ip"],
                "address": internal["ip"]
            },
            "url": {
                "full": f"http://{threat.get('domain', threat['ip'])}/payloads/{file_name}",
                "original": f"/payloads/{file_name}",
                "domain": threat.get("domain", threat["ip"])
            },
            "fortinet": {
                "firewall": {
                    "type": "utm",
                    "subtype": "virus",
                    "virus": malware_name,
                    "action": "blocked",
                    "vd": firewall["vd"]
                }
            },
            "related": {
                "ip": [threat["ip"], internal["ip"]]
            }
        }

        return {"raw": raw_syslog, "ecs": ecs_doc, "scenario": "virus"}

    # =========================================================================
    # MASTER EVENT DISPATCHER
    # =========================================================================

    def next_event(
        self,
        dt: datetime.datetime,
        threat_ratio: float = 0.10,
        scenario_filter: str = "all"
    ) -> Dict[str, Any]:
        """Generates the next synthetic event based on the scenario filter and threat ratio."""
        if scenario_filter == "baseline":
            return self.generate_baseline(dt)
        elif scenario_filter == "port_scan":
            return self.generate_port_scan(dt)
        elif scenario_filter == "c2_beacon":
            return self.generate_c2_beacon(dt)
        elif scenario_filter == "brute_force":
            return self.generate_login_attempt(dt, is_success=random.random() < 0.2)
        elif scenario_filter == "ips":
            return self.generate_utm_ips(dt)
        elif scenario_filter == "virus":
            return self.generate_utm_virus(dt)

        # "all" mode: 90% baseline traffic, 10% security threat detection scenarios
        is_threat = random.random() < threat_ratio
        if not is_threat:
            return self.generate_baseline(dt)

        # Distribute the 10% threats among detection scenarios
        threat_scenario = random.choices(
            ["port_scan", "c2_beacon", "brute_force", "ips", "virus"],
            weights=[30, 25, 20, 15, 10]
        )[0]

        if threat_scenario == "port_scan":
            return self.generate_port_scan(dt)
        elif threat_scenario == "c2_beacon":
            return self.generate_c2_beacon(dt)
        elif threat_scenario == "brute_force":
            return self.generate_login_attempt(dt, is_success=random.random() < 0.15)
        elif threat_scenario == "ips":
            return self.generate_utm_ips(dt)
        else:
            return self.generate_utm_virus(dt)
