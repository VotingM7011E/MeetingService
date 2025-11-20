from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
import os
import uuid

app = Flask(__name__)

# Load MongoDB URI
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
if not app.config["MONGO_URI"]:
    raise RuntimeError("MONGO_URI not set")

mongo = PyMongo(app)

# ---------------------------
# Utility functions
# ---------------------------

def to_uuid(id_str):
    """Validate and convert UUID string."""
    try:
        return str(uuid.UUID(id_str))
    except Exception:
        return None


def serialize_agenda_item(doc):
    """Convert MongoDB document into AgendaItem-format."""
    if not doc:
        return None

    item = {
        "type": doc["type"],
    }

    # Election item
    if doc["type"] == "election":
        item["title"] = doc["title"]
        item["positions"] = doc["positions"]

    # Motion item
    elif doc["type"] == "motion":
        item["title"] = doc["title"]
        item["description"] = doc["description"]
        item["base_motions"] = doc.get("base_motions", [])

    # Info item
    elif doc["type"] == "info":
        item["title"] = doc["title"]
        item["description"] = doc["description"]

    return item


def serialize_meeting(doc, items):
    """Combine meeting and agenda items into Meeting schema format."""
    return {
        "meeting_id": doc["meeting_id"],
        "meeting_name": doc["meeting_name"],
        "current_item": doc.get("current_item", 0),
        "items": [serialize_agenda_item(i) for i in items]
    }


# ---------------------------
# Routes matching OpenAPI spec
# ---------------------------

@app.post("/meetings")
def create_meeting():
    """
    POST /meetings
    Create a new meeting.
    """
    body = request.get_json()
    if not body or "meeting_name" not in body:
        return jsonify({"error": "meeting_name required"}), 400

    meeting_id = str(uuid.uuid4())

    mongo.db.meetings.insert_one({
        "meeting_id": meeting_id,
        "meeting_name": body["meeting_name"],
        "current_item": 0
    })

    created = {
        "meeting_id": meeting_id,
        "meeting_name": body["meeting_name"],
        "current_item": 0,
        "items": []
    }

    return jsonify(created), 201


@app.get("/meetings/<id>/")
def get_meeting(id):
    """
    GET /meetings/{id}/
    Return meeting info.
    """
    uid = to_uuid(id)
    if not uid:
        return jsonify({"error": "Invalid UUID"}), 400

    meeting = mongo.db.meetings.find_one({"meeting_id": uid})
    if not meeting:
        return jsonify({"error": "Meeting not found"}), 404

    agenda_items = list(mongo.db.agenda_items.find({"meeting_id": uid}))

    return jsonify(serialize_meeting(meeting, agenda_items)), 200


@app.post("/meetings/<id>/agenda")
def add_agenda_item(id):
    """
    POST /meetings/{id}/agenda
    Add an agenda item to meeting.
    """
    uid = to_uuid(id)
    if not uid:
        return jsonify({"error": "Invalid UUID"}), 400

    meeting = mongo.db.meetings.find_one({"meeting_id": uid})
    if not meeting:
        return jsonify({"error": "Meeting not found"}), 404

    body = request.get_json()
    if not body or "item" not in body:
        return jsonify({"error": "item required"}), 400

    item = body["item"]

    # Validate type (election, motion, info)
    if "type" not in item:
        return jsonify({"error": "Agenda item must include type"}), 400

    if item["type"] not in ["election", "motion", "info"]:
        return jsonify({"error": "Invalid agenda item type"}), 400

    # Insert agenda item under meeting
    mongo.db.agenda_items.insert_one({
        "meeting_id": uid,
        **item
    })

    return jsonify({"message": "Agenda item added"}), 201


@app.get("/meetings/<id>/agenda")
def get_agenda_items(id):
    """
    GET /meetings/{id}/agenda
    Returns all agenda items for the meeting.
    """
    uid = to_uuid(id)
    if not uid:
        return jsonify({"error": "Invalid UUID"}), 400

    meeting = mongo.db.meetings.find_one({"meeting_id": uid})
    if not meeting:
        return jsonify({"error": "Meeting not found"}), 404

    agenda_items = [
        serialize_agenda_item(i)
        for i in mongo.db.agenda_items.find({"meeting_id": uid})
    ]

    return jsonify(agenda_items), 200


# Root health check (for Kubernetes)
@app.get("/")
def root():
    return "MeetingService API running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
