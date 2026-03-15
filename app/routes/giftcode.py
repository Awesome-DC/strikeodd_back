from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User, GiftCode, GiftRedemption, Transaction, cap
import os, logging
try:
    import requests as http_requests
except ImportError:
    http_requests = None

giftcode_bp = Blueprint("giftcode", __name__)
logger = logging.getLogger(__name__)


@giftcode_bp.post("/redeem")
@jwt_required()
def redeem():
    user_id = get_jwt_identity()
    data    = request.get_json()
    code    = (data.get("code") or "").strip().upper()

    if not code:
        return jsonify({"error": "Enter a gift code"}), 400

    gc = GiftCode.query.filter_by(code=code, is_active=True).first()
    if not gc:
        return jsonify({"error": "Invalid or expired gift code"}), 404
    if gc.uses >= gc.max_uses:
        return jsonify({"error": "This gift code has already been fully redeemed"}), 400

    # Check if user already redeemed this code
    already = GiftRedemption.query.filter_by(code_id=gc.id, user_id=user_id).first()
    if already:
        return jsonify({"error": "You have already redeemed this code"}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Credit balance
    if gc.balance_type == "main":
        user.balance = cap(user.balance + gc.amount)
    else:
        user.bonus_balance = round((user.bonus_balance or 0) + gc.amount, 2)

    gc.uses += 1
    if gc.uses >= gc.max_uses:
        gc.is_active = False

    db.session.add(GiftRedemption(code_id=gc.id, user_id=user_id))
    db.session.add(Transaction(
        user_id=user_id, type="DEPOSIT", amount=gc.amount,
        reference=f"Gift code redeemed — {gc.code}",
        status="COMPLETED", balance_type=gc.balance_type
    ))
    db.session.commit()

    return jsonify({
        "message": f"🎁 Gift code redeemed! ₦{gc.amount:,.0f} added to your {'bonus' if gc.balance_type=='bonus' else 'main'} balance.",
        "amount": gc.amount,
        "balanceType": gc.balance_type,
        "newBalance": user.balance,
        "newBonusBalance": user.bonus_balance,
    })


@giftcode_bp.post("/telegram-create")
def telegram_create():
    """Called by Telegram bot webhook when admin sends /giftcode command."""
    data    = request.get_json(silent=True) or {}
    message = data.get("message", {})
    text    = message.get("text", "")
    chat_id = str(message.get("chat", {}).get("id", ""))
    admin_id = os.getenv("TELEGRAM_ADMIN_ID", "").strip()

    if chat_id != admin_id:
        return jsonify({"ok": True})

    # Format: /giftcode CODE AMOUNT MAXUSES [main|bonus]
    # e.g. /giftcode STRIKE500 5000 10 bonus
    if not text.startswith("/giftcode"):
        return jsonify({"ok": True})

    parts = text.split()
    if len(parts) < 3:
        _tg_reply(chat_id, "Usage: /giftcode CODE AMOUNT MAXUSES [bonus|main]\nExample: /giftcode STRIKE500 5000 10 bonus")
        return jsonify({"ok": True})

    code      = parts[1].upper()
    amount    = float(parts[2])
    max_uses  = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    bal_type  = parts[4] if len(parts) > 4 and parts[4] in ("bonus","main") else "bonus"

    existing = GiftCode.query.filter_by(code=code).first()
    if existing:
        _tg_reply(chat_id, f"❌ Code <b>{code}</b> already exists.")
        return jsonify({"ok": True})

    gc = GiftCode(code=code, amount=amount, max_uses=max_uses, balance_type=bal_type)
    db.session.add(gc)
    db.session.commit()

    _tg_reply(chat_id,
        f"✅ <b>Gift Code Created</b>\n\n"
        f"Code: <code>{code}</code>\n"
        f"Amount: ₦{amount:,.0f}\n"
        f"Max Uses: {max_uses}\n"
        f"Balance: {bal_type.upper()}"
    )
    return jsonify({"ok": True})


def _tg_reply(chat_id, text):
    token = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    if not token or not http_requests: return
    try:
        http_requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=5
        )
    except: pass
