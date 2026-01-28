import mesa
import random
import datetime
import sqlite3
from agents import Attacker, Defender
from scenarios import SCENARIOS

class NetworkModel(mesa.Model):
    def __init__(self, scenario_name=None, seed=None):
        super().__init__(seed=seed)
        
        # Initialize simulation time
        self.start_time = datetime.datetime.now()
        
        # Initialize Database
        self.init_db()
        
        if scenario_name is None:
            scenario_name = self.random.choice(list(SCENARIOS.keys()))
            
        self.attacker = Attacker(self, scenario_name=scenario_name)
        self.defender = Defender(self)
        
        self.datacollector = mesa.DataCollector(
            model_reporters={
                "Attacker_Goal": lambda m: m.attacker.current_goal,
                "Finished": lambda m: m.attacker.finished,
                "Has_Domain_Admin": lambda m: m.attacker.has_domain_admin
            }
        )
        
        self.running = True

    def init_db(self):
        conn = sqlite3.connect('simulation_logs.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS logs
                     (timestamp TEXT, agent_type TEXT, activity TEXT, status TEXT, details TEXT)''')
        conn.commit()
        conn.close()

    def step(self):
        self.agents.shuffle_do("step")
        self.datacollector.collect(self)
        
        if self.attacker.finished:
            self.running = False
            print(f"Model: Simulation finished - Scenario {self.attacker.scenario_name} completed.")
        elif self.steps > 150: # Increased timeout for more complex logic
            self.running = False
            print("Model: Simulation finished - Timeout reached.")

if __name__ == "__main__":
    model = NetworkModel()
    while model.running:
        model.step()
