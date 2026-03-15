"""
Push notification route.
Uses the Web Push Protocol (VAPID) via the `pywebpush` library.
Frontend subscribes → sends subscription JSON to /api/push/subscribe
Backend sends push on deposit approval & withdrawal update.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User
import os, json, logging

push_bp = Blueprint("push", __name__)
logger  = logging.getLogger(__name__)


def send_push(user, title, body, url="/"):
    """Send a push notification to a user. Silent fail if not set up."""
    if not user.push_subscription:
        return
    try:
        from pywebpush import webpush, WebPushException
        sub  = json.loads(user.push_subscription)
        data = json.dumps({"title": title, "body": body, "url": url})
        webpush(
            subscription_info=sub,
            data=data,
            vapid_private_key=os.getenv("VAPID_PRIVATE_KEY",""),
            vapid_claims={"sub": f"mailto:{os.getenv('VAPID_EMAIL','admin@strikeodds.com')}"},
        )
    except Exception as e:
        logger.warning(f"Push failed: {e}")


@push_bp.get("/vapid-public-key")
def vapid_public_key():
    return jsonify({"publicKey": os.getenv("VAPID_PUBLIC_KEY","")})


@push_bp.post("/subscribe")
@jwt_required()
def subscribe():
    user_id = get_jwt_identity()
    data    = request.get_json()
    sub     = data.get("subscription")
    if not sub:
        return jsonify({"error": "No subscription"}), 400
    user = User.query.get(user_id)
    user.push_subscription = json.dumps(sub)
    db.session.commit()
    return jsonify({"ok": True})


@push_bp.delete("/unsubscribe")
@jwt_required()
def unsubscribe():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    user.push_subscription = None
    db.session.commit()
    return jsonify({"ok": True})
