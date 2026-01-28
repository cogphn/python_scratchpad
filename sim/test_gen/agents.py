import mesa
import random
import datetime
import sqlite3
from scenarios import SCENARIOS, DEFENDER_CONFIG

class Credential:
    UNPRIVILEGED = "unprivileged"
    POWER_USER = "power user"
    DOMAIN_ADMIN = "domain administrator"
    
    LEVELS = [UNPRIVILEGED, POWER_USER, DOMAIN_ADMIN]

def log_to_db(timestamp, agent_type, activity, status, details):
    conn = sqlite3.connect('simulation_logs.db')
    c = conn.cursor()
    c.execute("INSERT INTO logs (timestamp, agent_type, activity, status, details) VALUES (?, ?, ?, ?, ?)",
              (timestamp.isoformat(), agent_type, activity, status, details))
    conn.commit()
    conn.close()

class Attacker(mesa.Agent):
    GOALS = ["Initial Access", "Persistence", "Privilege Escalation", "Lateral Movement", "Final Objectives"]

    def __init__(self, model, scenario_name=None):
        super().__init__(model)
        if scenario_name is None:
            scenario_name = random.choice(list(SCENARIOS.keys()))
        
        self.scenario_name = scenario_name
        self.path = SCENARIOS[scenario_name]
        self.current_goal = "Initial Access"
        self.credentials = []
        self.finished = False
        self.last_action_time = model.start_time

    def get_next_timestamp(self):
        delta = random.randint(1, 120)
        self.last_action_time += datetime.timedelta(minutes=delta)
        return self.last_action_time

    def step(self):
        if self.finished:
            return

        # Special case: Domain Admin immediately moves to Final Objectives
        if self.has_domain_admin and self.current_goal != "Final Objectives":
            ts = self.get_next_timestamp()
            print(f"[{ts}] Attacker: Domain Admin detected! Switching goal to Final Objectives.")
            log_to_db(ts, "Attacker", "Goal Transition", "Success", "Domain Admin obtained, switching to Final Objectives")
            self.current_goal = "Final Objectives"

        # Find techniques for the current goal in the scenario
        available_techniques = [t for t in self.path if t["stage"] == self.current_goal]
        
        # If no technique exists for this goal in the scenario, skip to next logical goal
        if not available_techniques:
            if self.current_goal == "Initial Access": self.current_goal = "Persistence"
            elif self.current_goal == "Persistence": self.current_goal = "Privilege Escalation"
            elif self.current_goal == "Privilege Escalation": self.current_goal = "Final Objectives"
            elif self.current_goal == "Lateral Movement": self.current_goal = "Privilege Escalation"
            elif self.current_goal == "Final Objectives": self.finished = True
            return

        action = random.choice(available_techniques)
        technique = action["technique"]
        base_prob = action["success_prob"]
        
        modifier = self.model.defender.get_modifier(technique, self)
        effective_prob = max(0, base_prob - modifier)
        
        ts = self.get_next_timestamp()
        print(f"[{ts}] Attacker: Attempting {technique} (Goal: {self.current_goal})")

        if random.random() < effective_prob:
            print(f"[{ts}] Attacker: Successfully executed {technique}")
            details = f"Technique: {technique}, Goal: {self.current_goal}"
            
            # Credential Access is often part of Privilege Escalation in our scenarios
            if self.current_goal == "Privilege Escalation":
                if random.random() < 0.20:
                    new_cred = Credential.DOMAIN_ADMIN
                    details += " | Obtained DOMAIN ADMIN"
                    print(f"[{ts}] Attacker: CRITICAL - Obtained DOMAIN ADMIN!")
                else:
                    new_cred = random.choice([Credential.UNPRIVILEGED, Credential.POWER_USER])
                    details += f" | Obtained {new_cred}"
                    print(f"[{ts}] Attacker: Obtained {new_cred} credentials.")
                self.credentials.append(new_cred)

            log_to_db(ts, "Attacker", technique, "Success", details)
            
            # Transition Goals on Success
            if self.current_goal == "Initial Access":
                self.current_goal = "Persistence"
            elif self.current_goal == "Persistence":
                self.current_goal = "Privilege Escalation"
            elif self.current_goal in ["Privilege Escalation", "Lateral Movement"]:
                self.current_goal = "Final Objectives"
            elif self.current_goal == "Final Objectives":
                self.finished = True
                print(f"[{ts}] Attacker: COMPLETED ALL OBJECTIVES!")
        else:
            print(f"[{ts}] Attacker: Failed {technique}")
            # Transition Goals on Failure
            if self.current_goal == "Privilege Escalation":
                print(f"[{ts}] Attacker: Cannot escalate privileges, attempting Lateral Movement.")
                self.current_goal = "Lateral Movement"

    @property
    def has_domain_admin(self):
        return Credential.DOMAIN_ADMIN in self.credentials

class Defender(mesa.Agent):
    def __init__(self, model):
        super().__init__(model)
        self.countermeasures = {}
        for technique, config in DEFENDER_CONFIG.items():
            self.countermeasures[config["cm"]] = {
                "mitigates": technique,
                "strength": config["strength"],
                "active": True
            }
        self.failure_rate = 0.3
        self.last_action_time = model.start_time

    def get_next_timestamp(self):
        delta = random.randint(1, 120)
        self.last_action_time += datetime.timedelta(minutes=delta)
        return self.last_action_time

    def get_modifier(self, technique, attacker_agent):
        modifier = 0
        for cm, info in self.countermeasures.items():
            if info["mitigates"] == technique and info["active"]:
                ts = self.get_next_timestamp()
                if random.random() < self.failure_rate:
                    print(f"[{ts}] Defender: Countermeasure '{cm}' FAILED!")
                    log_to_db(ts, "Defender", cm, "Failure", f"Failed to mitigate {technique}")
                    continue 
                modifier += info["strength"]
                log_to_db(ts, "Defender", cm, "Success", f"Actively mitigating {technique}")
        return modifier

    def step(self):
        ts = self.get_next_timestamp()
        print(f"[{ts}] Defender: Monitoring...")
        log_to_db(ts, "Defender", "Monitoring", "Success", "Routine network monitoring")
