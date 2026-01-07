#!/usr/bin/env python
"""Simple Flask server test"""
from flask import Flask

app = Flask(__name__)

@app.route('/test')
def test():
    return 'hello'

if __name__ == '__main__':
    print("Starting simple Flask server on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False)
