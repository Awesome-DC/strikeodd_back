from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User, Transaction
import os, re, logging
try:
    import requests as http_requests
except ImportError:
    http_requests = None
from datetime import datetime, timezone

withdraw_bp = Blueprint("withdraw", __name__)
logger = logging.getLogger(__name__)

NIGERIAN_BANKS = [
    "Access Bank","Citibank Nigeria","Ecobank Nigeria","Fidelity Bank",
    "First Bank of Nigeria","First City Monument Bank (FCMB)","Guaranty Trust Bank (GTBank)",
    "Heritage Bank","Keystone Bank","Polaris Bank","Providus Bank","Stanbic IBTC Bank",
    "Standard Chartered Bank","Sterling Bank","SunTrust Bank","Union Bank of Nigeria",
    "United Bank for Africa (UBA)","Unity Bank","Wema Bank","Zenith Bank",
    "Kuda Bank","Opay","Palmpay","Moniepoint","VFD Microfinance Bank",
    "Rubies Microfinance Bank","Carbon (One Finance)","FairMoney","Sparkle Bank",
]


def send_telegram_withdrawal(message: str, txn_id: str):
    token    = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    admin_id = os.getenv("TELEGRAM_ADMIN_ID", "").strip()

    print("\n" + "="*50)
    print("📨 WITHDRAWAL NOTIFICATION:")
    print(message)
    print("="*50 + "\n")

    if not token or not admin_id or token == "your-bot-token-here":
        logger.warning("Telegram not configured")
        return None

    if not http_requests:
        return None

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"wapprove_{txn_id}"},
            {"text": "❌ Decline", "callback_data": f"wdecline_{txn_id}"},
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
            return resp.json().get("result", {}).get("message_id")
        else:
            print(f"❌ Telegram error {resp.status_code}: {resp.text}")
            return None
    except Exception as e:
        print(f"❌ Telegram exception: {e}")
        return None


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


@withdraw_bp.get("/banks")
def get_banks():
    return jsonify({"banks": NIGERIAN_BANKS})


@withdraw_bp.get("/status")
@jwt_required()
def withdrawal_status():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    return jsonify({
        "setupComplete": bool(user and user.withdrawal_bank),
        "bankName":      user.withdrawal_bank if user else None,
        "accountNumber": user.withdrawal_account if user else None,
        "fullName":      user.withdrawal_name if user else None,
        "accountLast4":  user.withdrawal_account[-4:] if user and user.withdrawal_account else None,
    })


@withdraw_bp.post("/setup")
@jwt_required()
def setup_bank():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data           = request.get_json()
    account_number = data.get("accountNumber", "").strip()
    bank_name      = data.get("bankName", "").strip()
    full_name      = data.get("fullName", "").strip()
    pin            = data.get("pin", "").strip()

    if not account_number or not bank_name or not full_name or not pin:
        return jsonify({"error": "All fields are required"}), 400
    if not re.fullmatch(r"\d{10}", account_number):
        return jsonify({"error": "Account number must be exactly 10 digits"}), 400
    if bank_name not in NIGERIAN_BANKS:
        return jsonify({"error": f"'{bank_name}' is not a recognised Nigerian bank"}), 400
    if not re.fullmatch(r"\d{4}", pin):
        return jsonify({"error": "PIN must be exactly 4 digits"}), 400

    user.withdrawal_bank    = bank_name
    user.withdrawal_account = account_number
    user.withdrawal_name    = full_name
    user.withdrawal_pin     = pin
    db.session.commit()

    return jsonify({"message": "Bank details saved", "setupComplete": True})


@withdraw_bp.post("/update-details")
@jwt_required()
def update_details():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data           = request.get_json()
    account_number = data.get("accountNumber", "").strip()
    bank_name      = data.get("bankName", "").strip()
    full_name      = data.get("fullName", "").strip()
    current_pin    = data.get("currentPin", "").strip()

    if not current_pin:
        return jsonify({"error": "Current PIN is required to update bank details"}), 400
    if current_pin != user.withdrawal_pin:
        return jsonify({"error": "Incorrect PIN"}), 400
    if account_number and not re.fullmatch(r"\d{10}", account_number):
        return jsonify({"error": "Account number must be exactly 10 digits"}), 400
    if bank_name and bank_name not in NIGERIAN_BANKS:
        return jsonify({"error": f"'{bank_name}' is not a recognised Nigerian bank"}), 400

    if account_number: user.withdrawal_account = account_number
    if bank_name:      user.withdrawal_bank    = bank_name
    if full_name:      user.withdrawal_name    = full_name
    db.session.commit()

    return jsonify({"message": "Bank details updated successfully"})


@withdraw_bp.post("/change-pin")
@jwt_required()
def change_pin():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data        = request.get_json()
    current_pin = data.get("currentPin", "").strip()
    new_pin     = data.get("newPin", "").strip()

    if not current_pin or not new_pin:
        return jsonify({"error": "Both current and new PIN are required"}), 400
    if current_pin != user.withdrawal_pin:
        return jsonify({"error": "Incorrect current PIN"}), 400
    if not re.fullmatch(r"\d{4}", new_pin):
        return jsonify({"error": "New PIN must be exactly 4 digits"}), 400
    if current_pin == new_pin:
        return jsonify({"error": "New PIN must be different from current PIN"}), 400

    user.withdrawal_pin = new_pin
    db.session.commit()

    return jsonify({"message": "PIN changed successfully"})


@withdraw_bp.post("/request")
@jwt_required()
def request_withdrawal():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data   = request.get_json()
    amount = float(data.get("amount", 0))
    pin    = data.get("pin", "").strip()

    if not user.withdrawal_bank:
        return jsonify({"error": "Bank details not set up yet"}), 400
    if amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400
    if amount < 500:
        return jsonify({"error": "Minimum withdrawal is ₦500"}), 400
    if amount > user.balance:
        return jsonify({"error": "Insufficient balance"}), 400
    if pin != user.withdrawal_pin:
        return jsonify({"error": "Incorrect PIN"}), 400

    user.balance -= amount
    txn = Transaction(
        user_id=user_id,
        type="WITHDRAWAL",
        amount=-amount,
        reference=f"Withdrawal to {user.withdrawal_bank} — {user.withdrawal_account}",
        status="PENDING",
    )
    db.session.add(txn)
    db.session.commit()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = (
        f"💸 <b>WITHDRAWAL REQUEST</b>\n\n"
        f"👤 <b>Name:</b> {user.first_name} {user.last_name}\n"
        f"📧 <b>Email:</b> {user.email}\n"
        f"🏦 <b>Bank:</b> {user.withdrawal_bank}\n"
        f"🔢 <b>Account:</b> {user.withdrawal_account}\n"
        f"👤 <b>Account Name:</b> {user.withdrawal_name}\n"
        f"💰 <b>Amount:</b> ₦{amount:,.2f}\n"
        f"🕐 <b>Time:</b> {now}\n"
        f"🆔 <b>Txn ID:</b> {txn.id[:8].upper()}"
    )
    send_telegram_withdrawal(msg, txn.id)

    return jsonify({
        "message": "Withdrawal request submitted",
        "newBalance": user.balance,
        "transactionId": txn.id,
    })


@withdraw_bp.post("/telegram-webhook")
def withdrawal_telegram_webhook():
    """Telegram sends callback_query here when admin clicks Approve/Decline on withdrawal."""
    data = request.get_json(silent=True) or {}
    callback = data.get("callback_query")
    if not callback:
        return jsonify({"ok": True})

    cb_data = callback.get("data", "")
    msg_id  = callback.get("message", {}).get("message_id")
    chat_id = callback.get("message", {}).get("chat", {}).get("id")
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    if cb_data.startswith("wapprove_") or cb_data.startswith("wdecline_"):
        action = "approve" if cb_data.startswith("wapprove_") else "decline"
        txn_id = cb_data[len("wapprove_"):] if action == "approve" else cb_data[len("wdecline_"):]

        txn = Transaction.query.filter_by(id=txn_id).first()
        if not txn:
            _answer_callback(token, callback["id"], "Transaction not found")
            return jsonify({"ok": True})

        if txn.status != "PENDING":
            _answer_callback(token, callback["id"], f"Already {txn.status}")
            return jsonify({"ok": True})

        user = User.query.get(txn.user_id)

        if action == "approve":
            txn.status    = "COMPLETED"
            txn.reference = f"Withdrawal to {user.withdrawal_bank} — {user.withdrawal_account} — approved"
            db.session.commit()
            _edit_msg(token, chat_id, msg_id,
                f"✅ <b>WITHDRAWAL APPROVED</b>\n\n"
                f"₦{abs(txn.amount):,.2f} approved for {user.first_name} {user.last_name}\n"
                f"Bank: {user.withdrawal_bank} — {user.withdrawal_account}"
            )
            _answer_callback(token, callback["id"], "✅ Withdrawal approved!")
        else:
            # Decline — refund balance
            txn.status    = "FAILED"
            txn.reference = f"Withdrawal to {user.withdrawal_bank} — declined"
            user.balance  += abs(txn.amount)
            db.session.commit()
            _edit_msg(token, chat_id, msg_id,
                f"❌ <b>WITHDRAWAL DECLINED</b>\n\n"
                f"₦{abs(txn.amount):,.2f} refunded to {user.first_name} {user.last_name}'s balance."
            )
            _answer_callback(token, callback["id"], "❌ Withdrawal declined — balance refunded")

    return jsonify({"ok": True})


@withdraw_bp.get("/txn-status/<txn_id>")
@jwt_required()
def withdrawal_txn_status(txn_id):
    """Frontend can poll this to see if withdrawal was approved/declined."""
    user_id = get_jwt_identity()
    txn = Transaction.query.filter_by(id=txn_id, user_id=user_id).first()
    if not txn:
        return jsonify({"error": "Not found"}), 404
    user = User.query.get(user_id)
    return jsonify({
        "status":     txn.status,
        "newBalance": user.balance,
    })
