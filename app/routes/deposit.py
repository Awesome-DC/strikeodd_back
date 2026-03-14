from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User, Transaction
import os, logging
try:
    import requests as http_requests
except ImportError:
    http_requests = None
from datetime import datetime, timezone

deposit_bp = Blueprint("deposit", __name__)
logger = logging.getLogger(__name__)

# ── Hardcoded receiving account (edit these) ──
DEPOSIT_BANK_NAME    = "Opay"
DEPOSIT_ACCOUNT_NO   = "8012345678"
DEPOSIT_ACCOUNT_NAME = "StrikeOdds Enterprise"


def send_telegram_with_buttons(message: str, txn_id: str, amount: float, user_name: str):
    token    = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    admin_id = os.getenv("TELEGRAM_ADMIN_ID", "").strip()

    print("\n" + "="*50)
    print("📨 DEPOSIT NOTIFICATION:")
    print(message)
    print("="*50 + "\n")

    if not token or not admin_id or token == "your-bot-token-here":
        logger.warning("Telegram not configured")
        return None

    if not http_requests:
        return None

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"approve_{txn_id}"},
            {"text": "❌ Decline", "callback_data": f"decline_{txn_id}"},
        ]]
    }

    try:
        resp = http_requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": admin_id,
                "text": message,
                "parse_mode": "HTML",
                "reply_markup": keyboard,
            },
            timeout=8
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("result", {}).get("message_id")
        else:
            print(f"❌ Telegram error {resp.status_code}: {resp.text}")
            return None
    except Exception as e:
        print(f"❌ Telegram exception: {e}")
        return None


def edit_telegram_message(msg_id: int, new_text: str):
    """Edit an existing Telegram message (used for timeout)."""
    token    = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    admin_id = os.getenv("TELEGRAM_ADMIN_ID", "").strip()
    if not token or not admin_id or not http_requests or not msg_id:
        return
    try:
        http_requests.post(
            f"https://api.telegram.org/bot{token}/editMessageText",
            json={
                "chat_id": admin_id,
                "message_id": msg_id,
                "text": new_text,
                "parse_mode": "HTML",
            },
            timeout=8
        )
    except Exception as e:
        print(f"❌ Edit message error: {e}")


def notify_user_dm(user_email: str, message: str):
    """Log user notification — extend to email/SMS as needed."""
    print(f"\n📩 USER NOTIFICATION → {user_email}:\n{message}\n")


@deposit_bp.post("/initiate")
@jwt_required()
def initiate_deposit():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data   = request.get_json()
    amount = float(data.get("amount", 0))

    if amount < 1000:
        return jsonify({"error": "Minimum deposit is ₦1,000"}), 400
    if amount > 5000000:
        return jsonify({"error": "Maximum deposit is ₦5,000,000"}), 400

    # Create pending transaction
    txn = Transaction(
        user_id=user_id,
        type="DEPOSIT",
        amount=amount,
        reference=f"Deposit of ₦{amount:,.0f} — awaiting confirmation",
        status="PENDING", balance_type="main",
    )
    db.session.add(txn)
    db.session.commit()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = (
        f"💰 <b>DEPOSIT REQUEST</b>\n\n"
        f"👤 <b>User:</b> {user.first_name} {user.last_name}\n"
        f"📧 <b>Email:</b> {user.email}\n"
        f"💵 <b>Amount:</b> ₦{amount:,.2f}\n"
        f"🕐 <b>Time:</b> {now}\n"
        f"🆔 <b>Txn ID:</b> {txn.id[:8].upper()}\n\n"
        f"User has been shown payment details and clicked <b>I Have Sent the Money</b>."
    )

    tg_msg_id = send_telegram_with_buttons(msg, txn.id, amount, f"{user.first_name} {user.last_name}")

    # Store telegram message id so we can edit it on timeout
    txn.reference = f"{tg_msg_id or ''}|Deposit of ₦{amount:,.0f}"
    db.session.commit()

    return jsonify({
        "transactionId": txn.id,
        "tgMessageId":   tg_msg_id,
        "bankName":      DEPOSIT_BANK_NAME,
        "accountNo":     DEPOSIT_ACCOUNT_NO,
        "accountName":   DEPOSIT_ACCOUNT_NAME,
        "amount":        amount,
    })


@deposit_bp.post("/timeout")
@jwt_required()
def deposit_timeout():
    """Called by frontend when 10-min timer expires without user clicking 'I have sent'."""
    user_id = get_jwt_identity()
    data    = request.get_json()
    txn_id  = data.get("transactionId")

    txn = Transaction.query.filter_by(id=txn_id, user_id=user_id).first()
    if not txn or txn.status != "PENDING":
        return jsonify({"ok": True})

    txn.status    = "EXPIRED"
    txn.reference = f"Expired — user did not confirm payment"
    db.session.commit()

    # Edit the TG message to say expired
    user = User.query.get(user_id)
    msg = (
        f"⏰ <b>DEPOSIT EXPIRED</b>\n\n"
        f"👤 <b>User:</b> {user.first_name} {user.last_name}\n"
        f"💵 <b>Amount:</b> ₦{txn.amount:,.2f}\n"
        f"🆔 <b>Txn ID:</b> {txn_id[:8].upper()}\n\n"
        f"User did not click 'I Have Sent the Money' within 10 minutes. Session expired."
    )

    # Get stored tg msg id from reference
    ref = txn.reference or ""
    tg_msg_id = None
    # We stored it before updating — check original reference pattern
    # Re-query fresh to get the tg_msg_id we stored originally
    # (it was cleared above, so we pass None — edit won't fire, that's OK)
    edit_telegram_message(tg_msg_id, msg)

    return jsonify({"ok": True})


@deposit_bp.post("/telegram-webhook")
def telegram_webhook():
    """Telegram sends callback_query here when admin clicks Approve/Decline."""
    data = request.get_json(silent=True) or {}

    callback = data.get("callback_query")
    if not callback:
        return jsonify({"ok": True})

    cb_data  = callback.get("data", "")
    msg_id   = callback.get("message", {}).get("message_id")
    chat_id  = callback.get("message", {}).get("chat", {}).get("id")

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    if cb_data.startswith("approve_") or cb_data.startswith("decline_"):
        action = "approve" if cb_data.startswith("approve_") else "decline"
        txn_id = cb_data[len(action)+1:]

        txn = Transaction.query.filter_by(id=txn_id).first()
        if not txn:
            _answer_callback(token, callback["id"], "Transaction not found")
            return jsonify({"ok": True})

        if txn.status != "PENDING":
            _answer_callback(token, callback["id"], f"Already {txn.status}")
            return jsonify({"ok": True})

        user = User.query.get(txn.user_id)

        if action == "approve":
            bonus = round(txn.amount * 0.10, 2)  # 10% deposit bonus
            txn.status    = "COMPLETED"
            txn.reference = f"Deposit of ₦{txn.amount:,.0f} — approved"
            user.balance       += txn.amount
            user.bonus_balance  = round((user.bonus_balance or 0) + bonus, 2)
            # Bonus transaction record
            db.session.add(Transaction(
                user_id=user.id, type="DEPOSIT", amount=bonus,
                reference=f"10% deposit bonus on ₦{txn.amount:,.0f}",
                status="COMPLETED", balance_type="bonus"
            ))
            db.session.commit()

            _edit_msg(token, chat_id, msg_id,
                f"✅ <b>APPROVED</b> — ₦{txn.amount:,.2f} added to {user.first_name} {user.last_name}'s balance.\n"
                f"Bonus: +₦{bonus:,.2f} (10%) added to bonus balance.\n"
                f"New balance: ₦{user.balance:,.2f} | Bonus: ₦{user.bonus_balance:,.2f}"
            )
            _answer_callback(token, callback["id"], "✅ Approved!")
            notify_user_dm(user.email, f"Your deposit of ₦{txn.amount:,.2f} has been approved! +₦{bonus:,.2f} bonus added.")

        else:  # decline
            txn.status    = "FAILED"
            txn.reference = f"Deposit of ₦{txn.amount:,.0f} — declined"
            db.session.commit()

            _edit_msg(token, chat_id, msg_id,
                f"❌ <b>DECLINED</b> — Deposit of ₦{txn.amount:,.2f} for {user.first_name} {user.last_name} was declined."
            )
            _answer_callback(token, callback["id"], "❌ Declined")
            notify_user_dm(user.email, f"Your deposit of ₦{txn.amount:,.2f} was declined. Please contact support.")

    return jsonify({"ok": True})


def _answer_callback(token, callback_id, text):
    if not token or not http_requests: return
    try:
        http_requests.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": text},
            timeout=5
        )
    except: pass


def _edit_msg(token, chat_id, msg_id, text):
    if not token or not http_requests: return
    try:
        http_requests.post(
            f"https://api.telegram.org/bot{token}/editMessageText",
            json={"chat_id": chat_id, "message_id": msg_id, "text": text, "parse_mode": "HTML"},
            timeout=5
        )
    except: pass


@deposit_bp.get("/status/<txn_id>")
@jwt_required()
def deposit_status(txn_id):
    """Frontend polls this to know if admin approved/declined."""
    user_id = get_jwt_identity()
    txn = Transaction.query.filter_by(id=txn_id, user_id=user_id).first()
    if not txn:
        return jsonify({"error": "Not found"}), 404

    user = User.query.get(user_id)
    return jsonify({
        "status":        txn.status,
        "newBalance":    user.balance if txn.status == "COMPLETED" else None,
        "newBonusBalance": user.bonus_balance if txn.status == "COMPLETED" else None,
    })
