from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from app.crash_engine import engine

crash_bp = Blueprint("crash", __name__)

@crash_bp.get("/state")
@jwt_required()
def get_state():
    """Polled by Aviator + Crash Live every 100ms to sync round state."""
    return jsonify(engine.state())
