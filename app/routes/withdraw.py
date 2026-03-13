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


def send_telegram(message: str):
    token    = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    admin_id = os.getenv("TELEGRAM_ADMIN_ID", "").strip()

    # Always log to console so you can see it even without Telegram configured
    print("\n" + "="*50)
    print("📨 TELEGRAM NOTIFICATION:")
    print(message)
    print("="*50 + "\n")

    if not token or not admin_id or token == "your-bot-token-here":
        logger.warning("Telegram not configured — skipping. Set TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_ID in .env")
        return False

    if not http_requests:
        logger.warning("requests library not installed")
        return False

    try:
        resp = http_requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": admin_id, "text": message, "parse_mode": "HTML"},
            timeout=8
        )
        if resp.status_code == 200:
            print("✅ Telegram sent successfully")
            return True
        else:
            print(f"❌ Telegram error {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Telegram exception: {e}")
        return False


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
    """Update bank account details (requires current PIN to confirm)."""
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
    """Change withdrawal PIN."""
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
    send_telegram(msg)

    return jsonify({
        "message": "Withdrawal request submitted",
        "newBalance": user.balance,
        "transactionId": txn.id,
    })
