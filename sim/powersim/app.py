from flask import Flask, render_template, jsonify, request
from database import db, SimulationRun, SimulationStepRecord
from model import PowerPlantModel
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///simulation_history.db'
db.init_app(app)

# Global model instance
current_model = None
current_run_id = None

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_simulation():
    global current_model, current_run_id
    current_model = PowerPlantModel()
    
    new_run = SimulationRun(status="Active")
    db.session.add(new_run)
    db.session.commit()
    current_run_id = new_run.id
    
    return jsonify({"status": "Started", "run_id": current_run_id})

@app.route('/step', methods=['POST'])
def step_simulation():
    global current_model, current_run_id
    if not current_model:
        return jsonify({"error": "No active simulation"}), 400
    
    current_model.step()
    
    # Collect state
    df = current_model.datacollector.get_model_vars_dataframe()
    last_row = df.iloc[-1]
    
    neighborhoods = []
    for n in current_model.neighborhoods:
        neighborhoods.append({
            "id": n.unique_id,
            "is_critical": n.is_critical,
            "power_received": float(n.power_received),
            "demand": float(n.demand)
        })
    
    # Save to DB
    step_record = SimulationStepRecord(
        run_id=current_run_id,
        step_count=int(current_model.step_count),
        hour=int(last_row['Hour']),
        total_demand=float(last_row['Total Demand (kW)']),
        power_generated=float(last_row['Power Generated (kW)']),
        neighborhood_data=json.dumps(neighborhoods)
    )
    db.session.add(step_record)
    db.session.commit()
    
    return jsonify({
        "step": int(current_model.step_count),
        "hour": int(last_row['Hour']),
        "demand": float(last_row['Total Demand (kW)']),
        "generated": float(last_row['Power Generated (kW)']),
        "neighborhoods": neighborhoods
    })

@app.route('/attack', methods=['POST'])
def trigger_attack():
    global current_model
    if not current_model:
        return jsonify({"error": "No active simulation"}), 400
    
    # Cyber attack: 50% drop in generator efficiency
    current_model.generator.tamper(0.5)
    return jsonify({"status": "Attack Executed", "efficiency": current_model.generator.efficiency})

@app.route('/history', methods=['GET'])
def get_history():
    runs = SimulationRun.query.order_by(SimulationRun.start_time.desc()).all()
    return jsonify([{"id": r.id, "start_time": r.start_time.isoformat(), "status": r.status} for r in runs])

@app.route('/replay/<int:run_id>', methods=['GET'])
def replay_run(run_id):
    steps = SimulationStepRecord.query.filter_by(run_id=run_id).order_by(SimulationStepRecord.step_count).all()
    data = []
    for s in steps:
        data.append({
            "step": s.step_count,
            "hour": s.hour,
            "demand": s.total_demand,
            "generated": s.power_generated,
            "neighborhoods": json.loads(s.neighborhood_data)
        })
    return jsonify(data)

@app.route('/delete_history/<int:run_id>', methods=['DELETE'])
def delete_history(run_id):
    run = SimulationRun.query.get(run_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404
    
    # Delete associated steps first
    SimulationStepRecord.query.filter_by(run_id=run_id).delete()
    
    # Delete the run itself
    db.session.delete(run)
    db.session.commit()
    
    return jsonify({"status": "Deleted"})

@app.route('/run', methods=['POST'])
def run_simulation():
    global current_model, current_run_id
    if not current_model:
        return jsonify({"error": "No active simulation"}), 400
    
    try:
        data = request.get_json()
        count = int(data.get('count', 20))
    except (TypeError, ValueError):
        count = 20

    if count > 50:
        count = 50
    batch_results = []

    for _ in range(count):
        current_model.step()
        
        # Collect state for this step
        df = current_model.datacollector.get_model_vars_dataframe()
        last_row = df.iloc[-1]
        
        neighborhoods = []
        for n in current_model.neighborhoods:
            neighborhoods.append({
                "id": n.unique_id,
                "is_critical": n.is_critical,
                "power_received": float(n.power_received),
                "demand": float(n.demand)
            })
        
        # Save to DB
        step_record = SimulationStepRecord(
            run_id=current_run_id,
            step_count=current_model.step_count,
            hour=int(last_row['Hour']),
            total_demand=last_row['Total Demand (kW)'],
            power_generated=last_row['Power Generated (kW)'],
            neighborhood_data=json.dumps(neighborhoods)
        )
        db.session.add(step_record)
        
        # Add to batch response
        batch_results.append({
            "step": int(current_model.step_count),
            "hour": int(last_row['Hour']),
            "demand": float(last_row['Total Demand (kW)']),
            "generated": float(last_row['Power Generated (kW)']),
            "neighborhoods": neighborhoods
        })

    db.session.commit()
    return jsonify(batch_results)

@app.route('/remediate', methods=['POST'])
def remediate_attack():
    global current_model
    if not current_model:
        return jsonify({"error": "No active simulation"}), 400
    
    # Restore all components (Turbine, Generator, Transformer)
    current_model.turbine.remediate()
    current_model.generator.remediate()
    current_model.transformer.remediate()
    
    return jsonify({
        "status": "Remediated", 
        "generator_efficiency": float(current_model.generator.efficiency)
    })

@app.route('/update_efficiency', methods=['POST'])
def update_efficiency():
    global current_model
    if not current_model:
        return jsonify({"error": "No active simulation"}), 400
    
    data = request.get_json()
    component = data.get('component')
    value = float(data.get('value', 100)) / 100.0 # Convert 0-100 to 0.0-1.0
    
    if component == 'turbine':
        current_model.turbine.efficiency = value
    elif component == 'generator':
        current_model.generator.efficiency = value
    elif component == 'transformer':
        current_model.transformer.efficiency = value
    else:
        return jsonify({"error": "Invalid component"}), 400
        
    return jsonify({"status": "Updated", "component": component, "new_efficiency": value})

if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True, port=5003)
