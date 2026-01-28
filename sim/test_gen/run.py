import os
import sqlite3
from model import NetworkModel
from scenarios import SCENARIOS

def run_all_scenarios():
    # Clean up old database
    if os.path.exists('simulation_logs.db'):
        os.remove('simulation_logs.db')

    for scenario_name in SCENARIOS.keys():
        print(f"\n{'='*20}")
        print(f"RUNNING SCENARIO: {scenario_name}")
        print(f"{'='*20}")
        
        model = NetworkModel(scenario_name=scenario_name)
        while model.running:
            model.step()
        
        results = model.datacollector.get_model_vars_dataframe()
        print(f"\nScenario {scenario_name} Final State:")
        print(results.tail(1))
        
    print("\nSimulation Complete. Querying logs database sample...")
    
    # Display sample from database
    conn = sqlite3.connect('simulation_logs.db')
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY timestamp LIMIT 20")
    rows = c.fetchall()
    
    print(f"\n{'Timestamp':<25} | {'Agent':<10} | {'Activity':<25} | {'Status':<10}")
    print("-" * 80)
    for row in rows:
        print(f"{row[0]:<25} | {row[1]:<10} | {row[2]:<25} | {row[3]:<10}")
    
    conn.close()

if __name__ == "__main__":
    run_all_scenarios()
