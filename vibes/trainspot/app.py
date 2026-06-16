import os
from flask import Flask, render_template, jsonify
import requests

app = Flask(__name__)

# Allowed stations mapping to their myttc.ca URLs
STATIONS = {
    'king_station': {
        'name': 'King Station',
        'url': 'https://myttc.ca/king_station.json'
    },
    'woodbine_station': {
        'name': 'Woodbine Station',
        'url': 'https://myttc.ca/woodbine_station.json'
    }
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/map')
def map_page():
    return render_template('map.html')

@app.route('/api/data/<station_id>')
def get_data(station_id):
    if station_id not in STATIONS:
        return jsonify({"error": "Station not found or not supported"}), 404
    
    try:
        url = STATIONS[station_id]['url']
        # Fetch live data with 30s timeout
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return jsonify(response.json())
    except Exception as e:
        print(f"Error fetching data for {station_id}: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
