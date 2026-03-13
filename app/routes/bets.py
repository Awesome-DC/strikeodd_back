from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Bet, BetLeg, Odd, User, Transaction

bets_bp = Blueprint("bets", __name__)


@bets_bp.post("/")
@jwt_required()
def place_bet():
    user_id = get_jwt_identity()
    data = request.get_json()
    stake = data.get("stake")
    legs = data.get("legs", [])

    if not stake or stake < 1 or not legs:
        return jsonify({"error": "Invalid bet data"}), 400

    user = User.query.get(user_id)
    if user.balance < stake:
        return jsonify({"error": "Insufficient balance"}), 400

    odd_ids = [l["oddId"] for l in legs]
    odds = Odd.query.filter(Odd.id.in_(odd_ids), Odd.is_active == True).all()
    if len(odds) != len(legs):
        return jsonify({"error": "One or more odds are invalid"}), 400

    total_odds = round(eval("*".join(str(o.value) for o in odds)), 2)
    potential = round(stake * total_odds, 2)
    bet_type = "ACCUMULATOR" if len(legs) > 1 else "SINGLE"

    bet = Bet(
        user_id=user_id, type=bet_type,
        stake=stake, total_odds=total_odds, potential=potential
    )
    db.session.add(bet)
    db.session.flush()

    for odd in odds:
        db.session.add(BetLeg(bet_id=bet.id, odd_id=odd.id, odd_value=odd.value))

    user.balance = round(user.balance - stake, 2)
    db.session.add(Transaction(user_id=user_id, type="BET_PLACED", amount=-stake))
    db.session.commit()

    return jsonify({"bet": bet.to_dict(), "message": f"Bet placed! Potential win: ${potential}"}), 201


@bets_bp.get("/")
@jwt_required()
def get_my_bets():
    user_id = get_jwt_identity()
    status = request.args.get("status", "").upper()
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))

    query = Bet.query.filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status)

    total = query.count()
    bets = query.order_by(Bet.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    return jsonify({
        "bets": [b.to_dict() for b in bets],
        "total": total, "page": page,
        "pages": -(-total // limit)
    })


@bets_bp.post("/virtual-result")
@jwt_required()
def virtual_bet_result():
    """
    Handles two scenarios:
    1. roundId starts with "stake_deduct_" → just deduct stake (bet placed, waiting for kickoff)
    2. Normal roundId + won=True/False → credit winnings (bet settled at full time)
    """
    user_id  = get_jwt_identity()
    data     = request.get_json()
    stake    = float(data.get("stake", 0))
    won      = bool(data.get("won", False))
    payout   = float(data.get("payout", 0))
    round_id = data.get("roundId", "")

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    is_stake_deduct = round_id.startswith("stake_deduct_")
    is_win_only     = round_id.startswith(("av_win_", "dice_win_", "mines_win_", "pk_win_", "slot_win_", "bottle_win_", "plinko_win_", "coin_win_", "wheel_win_", "hilo_win_", "keno_win_", "tower_win_", "roulette_win_"))

    if is_win_only:
        # Credit winnings only — stake already deducted separately
        if won and payout > 0:
            user.balance = round(user.balance + payout, 2)
            db.session.add(Transaction(
                user_id=user_id, type="WIN",
                amount=payout,
                reference=f"Game Win — {round_id}"
            ))
    elif is_stake_deduct or stake > 0:
        # Deduct stake — any roundId that has a stake to deduct
        if stake <= 0 or user.balance < stake:
            return jsonify({"error": "Insufficient balance"}), 400
        user.balance = round(user.balance - stake, 2)
        game_name = "Virtual Football"
        if "av_" in round_id:      game_name = "Aviator"
        elif "dice_" in round_id:  game_name = "Dice Roll"
        elif "mines_" in round_id: game_name = "Mines"
        elif "pk_" in round_id:    game_name = "Penalty Shootout"
        elif "slot_" in round_id:    game_name = "Slot Machine"
        elif "bottle_" in round_id:  game_name = "Bottle Spin"
        elif "plinko_" in round_id:  game_name = "Plinko"
        elif "coin_" in round_id:    game_name = "Coin Flip"
        elif "wheel_" in round_id:   game_name = "Wheel of Fortune"
        elif "hilo_" in round_id:    game_name = "Hi-Lo"
        elif "keno_" in round_id:      game_name = "Keno"
        elif "tower_" in round_id:     game_name = "Tower Climb"
        elif "roulette_" in round_id:  game_name = "Roulette"
        db.session.add(Transaction(
            user_id=user_id, type="BET_PLACED",
            amount=-stake,
            reference=f"{game_name} Bet — {round_id}"
        ))
    else:
        # Settlement for virtual football wins
        if won and payout > 0:
            user.balance = round(user.balance + payout, 2)
            db.session.add(Transaction(
                user_id=user_id, type="WIN",
                amount=payout,
                reference=f"Virtual Football Win — {round_id}"
            ))

    db.session.commit()
    return jsonify({"newBalance": user.balance, "won": won, "payout": payout if won else 0})
