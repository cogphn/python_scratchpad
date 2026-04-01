from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class SimulationRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default="Active") # Active or Finished

class SimulationStepRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('simulation_run.id'))
    step_count = db.Column(db.Integer)
    hour = db.Column(db.Integer)
    total_demand = db.Column(db.Float)
    power_generated = db.Column(db.Float)
    # Store neighborhood states as a JSON string for replay
    # Format: [{"id": "nb_0", "critical": True, "powered": True, "demand": 120.5}, ...]
    neighborhood_data = db.Column(db.Text)
