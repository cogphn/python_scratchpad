import mesa
import random
import math

def get_critical_powered_percent(model):
    critical = [n for n in model.neighborhoods if n.is_critical]
    if not critical:
        return 0
    # Fully powered or degraded
    powered = [n for n in critical if n.power_received > 0]
    return (len(powered) / len(critical)) * 100

def get_standard_powered_percent(model):
    standard = [n for n in model.neighborhoods if not n.is_critical]
    if not standard:
        return 0
    powered = [n for n in standard if n.power_received > 0]
    return (len(powered) / len(standard)) * 100

def get_total_power_generated(model):
    return model.last_net_power

def get_total_demand(model):
    return sum(n.demand for n in model.neighborhoods)

class NeighborhoodAgent(mesa.Agent):
    """A neighborhood that consumes power."""
    def __init__(self, model, is_critical=False):
        super().__init__(model)
        self.is_critical = is_critical
        self.base_demand = random.uniform(80, 120) if is_critical else random.uniform(40, 70)
        self.demand = self.base_demand
        self.power_received = 0
        self.is_powered = False

    def update_demand(self):
        """Calculate demand based on time of day and random noise."""
        hour = self.model.step_count % 24
        time_multiplier = 1.0 + 0.4 * math.sin(math.pi * (hour - 8) / 12)
        noise = random.uniform(0.9, 1.1)
        shock = 2.0 if random.random() < 0.05 else 1.0
        self.demand = self.base_demand * time_multiplier * noise * shock

    def step(self):
        pass

class ComponentAgent(mesa.Agent):
    """Base class for Turbine, Generator, Transformer."""
    def __init__(self, model, efficiency=1.0, name=None):
        super().__init__(model)
        if name:
            self.unique_id = name
        self.is_on = True
        self.efficiency = efficiency
        self.is_tampered = False

    def toggle(self):
        self.is_on = not self.is_on

    def tamper(self, efficiency_drop):
        self.is_tampered = True
        self.efficiency = max(0, self.efficiency - efficiency_drop)

    def step(self):
        pass

class PowerPlantModel(mesa.Model):
    def __init__(self, num_neighborhoods=20, num_critical=3, fuel_input=2000):
        super().__init__()
        self.fuel_input = fuel_input
        self.last_net_power = 0
        self.step_count = 0
        
        # 1. Create Plant Components
        self.turbine = ComponentAgent(self, efficiency=0.9, name="turbine")
        self.generator = ComponentAgent(self, efficiency=0.95, name="generator")
        self.transformer = ComponentAgent(self, efficiency=0.98, name="transformer")
        
        # 2. Create Neighborhoods
        self.neighborhoods = []
        for i in range(num_neighborhoods):
            is_crit = (i < num_critical)
            n = NeighborhoodAgent(self, is_critical=is_crit)
            n.unique_id = f"nb_{i+1}" # Explicit string ID
            self.neighborhoods.append(n)

        # 3. Data Collector
        self.datacollector = mesa.DataCollector(
            model_reporters={
                "Hour": lambda m: m.step_count % 24,
                "Critical Powered %": get_critical_powered_percent,
                "Standard Powered %": get_standard_powered_percent,
                "Power Generated (kW)": get_total_power_generated,
                "Total Demand (kW)": get_total_demand,
                "Generator Efficiency": lambda m: m.generator.efficiency
            }
        )

    def step(self):
        self.step_count += 1
        
        # 1. Update all demands first
        for n in self.neighborhoods:
            n.update_demand()
            n.power_received = 0
            n.is_powered = False

        # 2. Calculate energy flow
        steam_output = self.fuel_input * self.turbine.efficiency if self.turbine.is_on else 0
        raw_power = steam_output * self.generator.efficiency if self.generator.is_on else 0
        self.last_net_power = raw_power * self.transformer.efficiency if self.transformer.is_on else 0
        
        # 3. Distribute power
        self.distribute_power(self.last_net_power)
        
        # 4. Collect data
        self.datacollector.collect(self)
        
        # 5. Advance agents (Mesa 3.x: agents are managed by the model)
        self.agents.shuffle_do("step")

    def distribute_power(self, available_power):
        # Sort: Critical first
        critical = [n for n in self.neighborhoods if n.is_critical]
        standard = [n for n in self.neighborhoods if not n.is_critical]

        for n in (critical + standard):
            n.power_received = min(available_power, n.demand)
            available_power -= n.power_received
            n.is_powered = n.power_received >= n.demand

if __name__ == "__main__":
    model = PowerPlantModel()
    
    print("Simulating 48 hours (2 full days)...")
    for i in range(48):
        model.step()
        df = model.datacollector.get_model_vars_dataframe()
        row = df.iloc[-1]
        print(f"Hour {int(row['Hour']):02d} | Demand: {row['Total Demand (kW)']:7.1f} | Gen: {row['Power Generated (kW)']:7.1f} | Crit: {row['Critical Powered %']:3.0f}% | Std: {row['Standard Powered %']:3.0f}%")
        
        # Simulate a noon attack on the second day
        if i == 36: # Hour 12 of second day
            print("\n--- ATTACK: Sabotaging Generator (Efficiency -40%) ---")
            model.generator.tamper(0.4)
