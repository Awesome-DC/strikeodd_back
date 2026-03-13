from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User, Transaction, Bet, BetLeg

users_bp = Blueprint("users", __name__)


@users_bp.get("/profile")
@jwt_required()
def profile():
    user = User.query.get(get_jwt_identity())
    return jsonify({"user": user.to_dict()})


@users_bp.get("/transactions")
@jwt_required()
def transactions():
    user_id = get_jwt_identity()
    txns = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.created_at.desc()).all()
    return jsonify({"transactions": [t.to_dict() for t in txns]})


@users_bp.delete("/account")
@jwt_required()
def delete_account():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Delete related records first (bets, transactions)
    # BetLegs are handled via Bet cascade
    for bet in Bet.query.filter_by(user_id=user_id).all():
        BetLeg.query.filter_by(bet_id=bet.id).delete()
    Bet.query.filter_by(user_id=user_id).delete()
    Transaction.query.filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()

    return jsonify({"message": "Account deleted"})
