
from flask import Flask, render_template, request
import sqlite3

app = Flask(__name__)

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

if __name__ == '__main__':
    app.run(debug=True)
