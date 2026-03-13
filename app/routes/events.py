from flask import Blueprint, request, jsonify
from app.models import Event, Sport

events_bp = Blueprint("events", __name__)


@events_bp.get("/")
def get_events():
    sport_slug = request.args.get("sport")
    status = request.args.get("status", "UPCOMING").upper()
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 20))

    query = Event.query.filter_by(status=status)
    if sport_slug:
        sport = Sport.query.filter_by(slug=sport_slug).first()
        if sport:
            query = query.filter_by(sport_id=sport.id)

    total = query.count()
    events = query.order_by(Event.start_time).offset((page - 1) * limit).limit(limit).all()

    return jsonify({
        "events": [e.to_dict() for e in events],
        "total": total, "page": page,
        "pages": -(-total // limit)
    })


@events_bp.get("/live")
def get_live():
    events = Event.query.filter_by(status="LIVE").order_by(Event.start_time).all()
    return jsonify({"events": [e.to_dict() for e in events]})


@events_bp.get("/<event_id>")
def get_event(event_id):
    event = Event.query.get_or_404(event_id)
    return jsonify({"event": event.to_dict()})
