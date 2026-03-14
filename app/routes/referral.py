from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User

referral_bp = Blueprint("referral", __name__)

@referral_bp.get("/info")
@jwt_required()
def referral_info():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    referrals = User.query.filter_by(referred_by=user_id).order_by(User.created_at.desc()).all()

    return jsonify({
        "refCode":    user.ref_code,
        "refLink":    f"https://strikeodd.vercel.app/auth?ref={user.ref_code}",
        "totalRefs":  len(referrals),
        "totalEarned": len(referrals) * 200,
        "referrals": [{
            "username":  r.username,
            "joinedAt":  r.created_at.isoformat(),
        } for r in referrals],
    })
