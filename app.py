from flask import Flask, request, jsonify, make_response
from flask import Blueprint

from flask_pymongo import PyMongo
from keycloak_auth import keycloak_protect
import os
import uuid
import random

blueprint = Blueprint('blueprint', __name__)

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

def generate_unique_meeting_code():
    """Generate a unique 6-digit meeting code."""
    while True:
        code = f"{random.randint(0, 999999):06d}"  # always 6 digits
        existing = mongo.db.meetings.find_one({"meeting_code": code})
        if not existing:
            return code

def serialize_meeting(doc, items):
    """Combine meeting and agenda items into Meeting schema format."""
    return {
        "meeting_id": doc["meeting_id"],
        "meeting_name": doc["meeting_name"],
        "current_item": doc.get("current_item", 0),
        "items": items
    }

def verify_agenda_item(item):
    """Verify that agenda item is of proper type and has proper data"""
    if "type" not in item:
        return jsonify({"error": "Agenda item must include type"}), 400

    if ("title" not in item) or (type(item["title"]) is str):
        return jsonify({"error": "Agenda item must have title"}), 400

    match item["type"]:
        case "election":
            if "positions" not in item or not (type(item["positions"]) is list):
                return jsonify({"error": "Election agenda item must have positions list"}), 400
            for position in type["positions"]:
                if not (type(position) is str):
                    return jsonify({"error": "Election agenda item positions must be strings"}), 400
        case "motion":
            if "description" not in item or not (type(item["description"]) is str):
                return jsonify({"error": "Motion agenda item must have description"}), 400

            if "baseMotions" not in item or not (type(item["baseMotions"]) is list):
                return jsonify({"error": "Motion agenda item must have baseMotions list"}), 400
            for baseMotion in type["baseMotions"]:
                if not (type(baseMotion) is object):
                    return jsonify({"error": "Motion agenda item baseMotions must be objects"}), 400

                if "owner" not in baseMotion or not (type(baseMotion["owner"]) is str):
                    return jsonify({"error": "Motion agenda item baseMotions must have owner"}), 400
                
                if "motion" not in baseMotion or not (type(baseMotion["motion"]) is str):
                    return jsonify({"error": "Motion agenda item baseMotions must have motion"}), 400
                    
        case "info":
            if "description" not in item or not (type(item["description"]) is str):
                return jsonify({"error": "Info agenda item must have description"}), 400
            
        case _:
            return jsonify({"error": "Invalid agenda item type"}), 400
            
    return None

def serialize_agenda_item(item):
    """Verifies agenda item and return only proper data fields"""
    result = verify_agenda_item(item)
    if result is not None:
        return None
    
    match item["type"]:
        case "election":
            return {
                "type": item["type"],
                "title": item["title"],
                "positions": item["positions"] 
            }
        case "motion":
            return {
                "type": item["type"],
                "title": item["title"],
                "description": item["description"],
                "baseMotions": item["baseMotions"]
            }       
        case "info":
            return {
                "type": item["type"],
                "title": item["title"],
                "description": item["description"] 
            }
        case _:
            return None
# ---------------------------
# Endpoints
# ---------------------------

# put this sippet ahead of all your bluprints
# blueprint can also be app~~
@blueprint.after_request 
def after_request(response):
    header = response.headers
    header['Access-Control-Allow-Origin'] = '*'
    header['Access-Control-Allow-Headers'] = "*"
    header['Access-Control-Allow-Methods'] = "*"
    # Other headers can be added here if needed
    return response

@blueprint.post("/meetings")
def create_meeting():
    """
    POST /meetings
    Create a new meeting.
    """
    body = request.get_json()
    if not body or "meeting_name" not in body:
        return jsonify({"error": "meeting_name required"}), 400

    meeting_id = str(uuid.uuid4())
    meeting_code = generate_unique_meeting_code()

    mongo.db.meetings.insert_one({
        "meeting_id": meeting_id,
        "meeting_name": body["meeting_name"],
        "current_item": 0,
        "meeting_code": meeting_code
    })

    created = {
        "meeting_id": meeting_id,
        "meeting_name": body["meeting_name"],
        "current_item": 0,
        "items": [],
        "meeting_code": meeting_code
    }

    return jsonify(created), 201

@blueprint.get("/meetings/<id>/")
def get_meeting(id):
    """
    GET /meetings/{id}/
    Return meeting info.
    """
    if request.method == "OPTIONS": # CORS preflight
        return _build_cors_preflight_response()
    elif request.method == "GET":
        uid = to_uuid(id)
        if not uid:
            return jsonify({"error": "Invalid UUID"}), 400

        meeting = mongo.db.meetings.find_one({"meeting_id": uid})
        if not meeting:
            return jsonify({"error": "Meeting not found"}), 404

        agenda_items = list(mongo.db.agenda_items.find({"meeting_id": uid}))

        return jsonify(serialize_meeting(meeting, agenda_items)), 200

@blueprint.patch("/meetings/<id>")
def update_meeting(id):
    """
    PATCH /meetings/{id}
    Update meeting fields such as current_item.
    """
    
    uid = to_uuid(id)
    if not uid:
        return jsonify({"error": "Invalid UUID"}), 400

    meeting = mongo.db.meetings.find_one({"meeting_id": uid})
    if not meeting:
        return jsonify({"error": "Meeting not found"}), 404

    body = request.get_json()
    if not body:
        return jsonify({"error": "Request body required"}), 400

    update_fields = {}

    # Validate and update current_item
    if "current_item" in body:
        new_index = body["current_item"]

        if type(new_index) is not int or new_index < 0:
            return jsonify({"error": "current_item must be a non-negative integer"}), 400

        # Count agenda items
        item_count = mongo.db.agenda_items.count_documents({"meeting_id": uid})

        # Check if index is within valid range
        if new_index >= item_count:
            return jsonify({
                "error": "current_item is out of range",
                "max_valid_index": max(item_count - 1, 0),
                "agenda_items": item_count
            }), 400

        update_fields["current_item"] = new_index

    if not update_fields:
        return jsonify({"error": "No valid fields to update"}), 400

    # Apply patch
    mongo.db.meetings.update_one(
        {"meeting_id": uid},
        {"$set": update_fields}
    )

    # Return updated meeting
    updated_meeting = mongo.db.meetings.find_one({"meeting_id": uid})
    items = list(mongo.db.agenda_items.find({"meeting_id": uid}))

    return jsonify(serialize_meeting(updated_meeting, items)), 200

@blueprint.post("/meetings/<id>/agenda")
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

    item = serialize_agenda_item(body["item"])
    if item is None:
        return jsonify({"error": "Invalid agenda item type"}), 400

    # Insert agenda item under meeting
    mongo.db.agenda_items.insert_one({
        "meeting_id": uid,
        **item
    })

    return jsonify({"message": "Agenda item added"}), 201

@blueprint.get("/meetings/<id>/agenda")
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

    agenda_items = list(mongo.db.agenda_items.find({"meeting_id": uid}))

    return jsonify(agenda_items), 200

@blueprint.get("/code/<code>")
def get_meeting_id_from_code(code):
    """
    GET /code/{code}
    Returns the meeting UUID in plain text.
    """
    # Validate length & numeric
    if len(code) != 6 or not code.isdigit():
        return jsonify({"error": "Invalid meeting code format"}), 400

    meeting = mongo.db.meetings.find_one({"meeting_code": code})
    if not meeting:
        return "", 404

    return meeting["meeting_id"], 200

# Root health check (for Kubernetes)
@app.get("/")
def root():
    return "MeetingService API running"

@app.route("/private")
@keycloak_protect
def private():
    return jsonify({
        "message": "Protected route",
        "user": request.user
    })

@app.route("/public")
def public():
    return {"message": "Public route"}

app.register_blueprint(blueprint)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
