from flask import Blueprint, jsonify
from app.models import Sport

sports_bp = Blueprint("sports", __name__)


@sports_bp.get("/")
def get_sports():
    sports = Sport.query.filter_by(is_active=True).all()
    return jsonify({"sports": [s.to_dict() for s in sports]})
