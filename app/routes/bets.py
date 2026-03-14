from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, Bet, BetLeg, Odd, User, Transaction, cap

bets_bp = Blueprint("bets", __name__)


@bets_bp.post("/")
@jwt_required()
def place_bet():
    user_id = get_jwt_identity()
    data    = request.get_json()
    stake   = data.get("stake")
    legs    = data.get("legs", [])
    if not stake or stake < 1 or not legs:
        return jsonify({"error": "Invalid bet data"}), 400

    user = User.query.get(user_id)
    if user.balance < stake:
        return jsonify({"error": "Insufficient balance"}), 400

    odd_ids = [l["oddId"] for l in legs]
    odds    = Odd.query.filter(Odd.id.in_(odd_ids), Odd.is_active == True).all()
    if len(odds) != len(legs):
        return jsonify({"error": "One or more odds are invalid"}), 400

    total_odds = round(eval("*".join(str(o.value) for o in odds)), 2)
    potential  = round(stake * total_odds, 2)
    bet_type   = "ACCUMULATOR" if len(legs) > 1 else "SINGLE"

    bet = Bet(user_id=user_id, type=bet_type, stake=stake, total_odds=total_odds, potential=potential)
    db.session.add(bet)
    db.session.flush()

    for odd in odds:
        db.session.add(BetLeg(bet_id=bet.id, odd_id=odd.id, odd_value=odd.value))

    user.balance = cap(user.balance - stake)
    db.session.add(Transaction(user_id=user_id, type="BET_PLACED", amount=-stake, balance_type="main"))
    db.session.commit()
    return jsonify({"bet": bet.to_dict(), "message": f"Bet placed! Potential win: ₦{potential}"}), 201


@bets_bp.get("/")
@jwt_required()
def get_my_bets():
    user_id = get_jwt_identity()
    status  = request.args.get("status", "").upper()
    page    = int(request.args.get("page", 1))
    limit   = int(request.args.get("limit", 10))
    query   = Bet.query.filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status)
    total = query.count()
    bets  = query.order_by(Bet.created_at.desc()).offset((page-1)*limit).limit(limit).all()
    return jsonify({"bets": [b.to_dict() for b in bets], "total": total, "page": page, "pages": -(-total//limit)})


@bets_bp.post("/virtual-result")
@jwt_required()
def virtual_bet_result():
    """
    Handles game bet/win settlements.
    useBonus=true → stake from bonus_balance, only profit → main balance
    useBonus=false → stake from main balance, full payout → main balance
    """
    user_id  = get_jwt_identity()
    data     = request.get_json()
    stake    = float(data.get("stake", 0))
    won      = bool(data.get("won", False))
    payout   = float(data.get("payout", 0))
    round_id = data.get("roundId", "")
    use_bonus = bool(data.get("useBonus", False))

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    is_win_only  = round_id.startswith(("av_win_","dice_win_","mines_win_","pk_win_","slot_win_",
                                         "bottle_win_","plinko_win_","coin_win_","wheel_win_",
                                         "hilo_win_","keno_win_","tower_win_","roulette_win_",
                                         "bj_win_","crash_mp_win_", "shell_win_"))
    is_stake_deduct = round_id.startswith("stake_deduct_") or stake > 0

    game_name = _game_name(round_id)

    if is_win_only:
        # Win credit only — stake already deducted
        if won and payout > 0:
            if use_bonus:
                # Only profit (payout - stake) goes to main balance
                profit = round(payout - stake, 2) if stake > 0 else payout
                profit = max(0, profit)
                user.balance = cap(user.balance + profit)
                db.session.add(Transaction(
                    user_id=user_id, type="WIN", amount=profit,
                    reference=f"{game_name} Win (bonus) — {round_id}",
                    status="COMPLETED", balance_type="main"
                ))
            else:
                user.balance = cap(user.balance + payout)
                db.session.add(Transaction(
                    user_id=user_id, type="WIN", amount=payout,
                    reference=f"{game_name} Win — {round_id}",
                    status="COMPLETED", balance_type="main"
                ))

    elif is_stake_deduct:
        if use_bonus:
            # Round both to 2dp to avoid float precision issues (e.g. 299.999 < 300)
            bonus_bal = round(user.bonus_balance or 0, 2)
            stake_r   = round(stake, 2)
            if stake_r <= 0 or bonus_bal < stake_r:
                return jsonify({"error": "Insufficient bonus balance"}), 400
            user.bonus_balance = round(bonus_bal - stake_r, 2)
            db.session.add(Transaction(
                user_id=user_id, type="BET_PLACED", amount=-stake,
                reference=f"{game_name} Bet (bonus) — {round_id}",
                status="COMPLETED", balance_type="bonus"
            ))
        else:
            if stake <= 0 or user.balance < stake:
                return jsonify({"error": "Insufficient balance"}), 400
            user.balance = cap(user.balance - stake)
            db.session.add(Transaction(
                user_id=user_id, type="BET_PLACED", amount=-stake,
                reference=f"{game_name} Bet — {round_id}",
                status="COMPLETED", balance_type="main"
            ))

    else:
        # Virtual football settlement
        if won and payout > 0:
            user.balance = cap(user.balance + payout)
            db.session.add(Transaction(
                user_id=user_id, type="WIN", amount=payout,
                reference=f"Virtual Football Win — {round_id}",
                status="COMPLETED", balance_type="main"
            ))

    db.session.commit()
    return jsonify({
        "newBalance": user.balance,
        "newBonusBalance": user.bonus_balance,
        "won": won,
        "payout": payout if won else 0
    })


def _game_name(round_id):
    for prefix, name in [
        ("av_","Aviator"),("dice_","Dice Roll"),("mines_","Mines"),
        ("pk_","Penalty Shootout"),("slot_","Slot Machine"),("bottle_","Bottle Spin"),
        ("plinko_","Plinko"),("coin_","Coin Flip"),("wheel_","Wheel of Fortune"),
        ("hilo_","Hi-Lo"),("keno_","Keno"),("tower_","Tower Climb"),
        ("roulette_","Roulette"),("bj_","Blackjack"),("crash_mp_","Crash Live"),
        ("shell_","Shell Game"),
    ]:
        if prefix in round_id:
            return name
    return "Virtual Football"
