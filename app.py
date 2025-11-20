from flask import Flask, jsonify
from flask_pymongo import PyMongo
import os

app = Flask(__name__)

app.config["MONGO_URI"] = os.getenv("MONGO_URI")

mongo = PyMongo(app)

@app.route('/')
def hello():
    return 'Hello from GHCR + Argo CD!'

@app.route("/testdb")
def test_db():
    # Insert a test document
    mongo.db.testcollection.insert_one({"status": "ok"})

    # Fetch documents
    docs = list(mongo.db.testcollection.find({}, {"_id": 0}))

    return jsonify({"documents": docs})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)