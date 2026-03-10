
from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('rules.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS environments (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS observed_techniques (
            id INTEGER PRIMARY KEY,
            technique_id TEXT,
            environment_id INTEGER,
            FOREIGN KEY (technique_id) REFERENCES techniques(id),
            FOREIGN KEY (environment_id) REFERENCES environments(id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS developed_detections (
            id INTEGER PRIMARY KEY,
            observed_technique_id INTEGER,
            detection_count INTEGER,
            detection_type TEXT,
            query TEXT,
            notes TEXT,
            coverage_confidence TEXT,
            FOREIGN KEY (observed_technique_id) REFERENCES observed_techniques(id)
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search')
def search():
    query = request.args.get('q')
    conn = sqlite3.connect('rules.db')
    c = conn.cursor()
    c.execute("SELECT name, src, url FROM rules WHERE name LIKE ?", ('%' + query + '%',))
    results = c.fetchall()
    conn.close()
    return render_template('index.html', results=results, query=query)

@app.route('/observed', methods=['GET', 'POST'])
def observed():
    conn = sqlite3.connect('rules.db')
    c = conn.cursor()

    if request.method == 'POST':
        technique_id = request.form['technique']
        environment_name = request.form['environment']

        c.execute("SELECT id FROM environments WHERE name = ?", (environment_name,))
        env = c.fetchone()
        if env:
            env_id = env[0]
        else:
            c.execute("INSERT INTO environments (name) VALUES (?)", (environment_name,))
            conn.commit()
            env_id = c.lastrowid
        
        c.execute("INSERT INTO observed_techniques (technique_id, environment_id) VALUES (?, ?)", (technique_id, env_id))
        conn.commit()
        conn.close()
        return redirect(url_for('observed'))

    c.execute("SELECT external_id, name FROM techniques")
    techniques = c.fetchall()
    
    c.execute("""
        SELECT ot.id, t.external_id, t.name, e.name 
        FROM observed_techniques ot
        JOIN techniques t ON ot.technique_id = t.external_id
        JOIN environments e ON ot.environment_id = e.id
    """)
    observed_techniques = c.fetchall()
    
    conn.close()
    return render_template('observed.html', techniques=techniques, observed_techniques=observed_techniques)

@app.route('/developed', methods=['GET', 'POST'])
def developed():
    conn = sqlite3.connect('rules.db')
    c = conn.cursor()

    if request.method == 'POST':
        observed_technique_id = request.form['observed_technique']
        detection_count = request.form['detection_count']
        detection_type = request.form['detection_type']
        query = request.form['query']
        notes = request.form['notes']
        coverage_confidence = request.form['coverage_confidence']
        
        c.execute("""
            INSERT INTO developed_detections (observed_technique_id, detection_count, detection_type, query, notes, coverage_confidence)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (observed_technique_id, detection_count, detection_type, query, notes, coverage_confidence))
        conn.commit()
        conn.close()
        return redirect(url_for('developed'))

    c.execute("""
        SELECT ot.id, t.external_id, t.name, e.name
        FROM observed_techniques ot
        JOIN techniques t ON ot.technique_id = t.external_id
        JOIN environments e ON ot.environment_id = e.id
    """)
    observed_techniques = c.fetchall()

    c.execute("""
        SELECT t.external_id, t.name, e.name, dd.detection_count, dd.detection_type, dd.query, dd.notes, dd.coverage_confidence
        FROM developed_detections dd
        JOIN observed_techniques ot ON dd.observed_technique_id = ot.id
        JOIN techniques t ON ot.technique_id = t.external_id
        JOIN environments e ON ot.environment_id = e.id
    """)
    developed_detections = c.fetchall()
    
    conn.close()
    return render_template('developed.html', observed_techniques=observed_techniques, developed_detections=developed_detections)

@app.route('/dashboard')
def dashboard():
    conn = sqlite3.connect('rules.db')
    c = conn.cursor()

    c.execute("SELECT DISTINCT technique_id FROM observed_techniques")
    technique_ids = [row[0] for row in c.fetchall()]

    coverage_data = []
    for tech_id in technique_ids:
        c.execute("SELECT COUNT(*) FROM observed_techniques WHERE technique_id = ?", (tech_id,))
        total_observations = c.fetchone()[0]

        c.execute("""
            SELECT COUNT(*)
            FROM developed_detections dd
            JOIN observed_techniques ot ON dd.observed_technique_id = ot.id
            WHERE ot.technique_id = ? AND dd.coverage_confidence IN ('medium', 'medium-high', 'high')
        """, (tech_id,))
        medium_confidence_detections = c.fetchone()[0]

        c.execute("SELECT e.name FROM observed_techniques ot JOIN environments e ON ot.environment_id = e.id WHERE ot.technique_id = ?", (tech_id,))
        observed_envs = {row[0] for row in c.fetchall()}

        c.execute("""
            SELECT e.name
            FROM developed_detections dd
            JOIN observed_techniques ot ON dd.observed_technique_id = ot.id
            JOIN environments e ON ot.environment_id = e.id
            WHERE ot.technique_id = ? AND dd.coverage_confidence IN ('medium', 'medium-high', 'high')
        """, (tech_id,))
        covered_envs = {row[0] for row in c.fetchall()}

        color = ''
        percentage = 0
        if total_observations > 0:
            percentage = (medium_confidence_detections / total_observations) * 100

        if observed_envs and observed_envs.issubset(covered_envs):
            color = 'green'
            percentage = 100
        elif percentage < 50:
            color = 'red'
        else:
            color = 'orange'

        coverage_data.append({
            'technique_id': tech_id,
            'percentage': f"{percentage:.2f}%",
            'color': color
        })

    conn.close()
    return render_template('dashboard.html', coverage_data=coverage_data)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
