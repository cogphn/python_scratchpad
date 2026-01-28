# Scenarios with standardized stages for the state machine

SCENARIOS = {
    "Emotet_Trickbot_CobaltStrike": [
        {"technique": "Spearphishing Link", "stage": "Initial Access", "success_prob": 0.4},
        {"technique": "Process Injection", "stage": "Persistence", "success_prob": 0.5},
        {"technique": "Credentials from Web Browsers", "stage": "Privilege Escalation", "success_prob": 0.6},
        {"technique": "SMB/Windows Admin Shares", "stage": "Lateral Movement", "success_prob": 0.4},
        {"technique": "Data Encrypted for Impact", "stage": "Final Objectives", "success_prob": 0.7}
    ],
    "IcedID_to_Ransomware": [
        {"technique": "Spearphishing Attachment", "stage": "Initial Access", "success_prob": 0.3},
        {"technique": "Scheduled Task", "stage": "Persistence", "success_prob": 0.5},
        {"technique": "OS Credential Dumping", "stage": "Privilege Escalation", "success_prob": 0.4},
        {"technique": "Remote Desktop Protocol", "stage": "Lateral Movement", "success_prob": 0.5},
        {"technique": "Data Exfiltration to Cloud", "stage": "Final Objectives", "success_prob": 0.6}
    ],
    "Bumblebee_to_Conti": [
        {"technique": "ISO Image", "stage": "Initial Access", "success_prob": 0.5},
        {"technique": "Registry Run Keys", "stage": "Persistence", "success_prob": 0.6},
        {"technique": "Kerberoasting", "stage": "Privilege Escalation", "success_prob": 0.4},
        {"technique": "PsExec", "stage": "Lateral Movement", "success_prob": 0.6},
        {"technique": "Inhibit System Recovery", "stage": "Final Objectives", "success_prob": 0.7}
    ]
}

DEFENDER_CONFIG = {
    "Spearphishing Link": {"cm": "Email Filtering", "strength": 0.3},
    "Spearphishing Attachment": {"cm": "Sandboxing", "strength": 0.4},
    "Process Injection": {"cm": "EDR", "strength": 0.5},
    "Registry Run Keys": {"cm": "Persistence Monitoring", "strength": 0.3},
    "Scheduled Task": {"cm": "Task Audit", "strength": 0.3},
    "Credentials from Web Browsers": {"cm": "Browser Isolation", "strength": 0.4},
    "OS Credential Dumping": {"cm": "LSASS Protection", "strength": 0.6},
    "SMB/Windows Admin Shares": {"cm": "Network Segmentation", "strength": 0.5},
    "Remote Desktop Protocol": {"cm": "MFA", "strength": 0.6},
    "PsExec": {"cm": "Privileged Access Management", "strength": 0.5},
    "Data Encrypted for Impact": {"cm": "Backup & DR", "strength": 0.2},
    "Data Exfiltration to Cloud": {"cm": "DLP", "strength": 0.4},
    "ISO Image": {"cm": "File Extension Filtering", "strength": 0.3},
    "System Information Discovery": {"cm": "Internal Monitoring", "strength": 0.2},
    "Kerberoasting": {"cm": "Active Directory Hardening", "strength": 0.4},
    "Inhibit System Recovery": {"cm": "Immutable Backups", "strength": 0.5},
    "Token Manipulation": {"cm": "Access Control", "strength": 0.3},
    "Kernel Exploit": {"cm": "Patch Management", "strength": 0.5}
}
