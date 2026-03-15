from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User, Transaction, GiftCode, GiftRedemption, Bet, BetLeg, cap
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
import os, bcrypt

admin_bp = Blueprint("admin", __name__)

def require_admin():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)
    if not user or user.role != "ADMIN":
        return None, (jsonify({"error": "Admin access required"}), 403)
    return user, None

# ── Telegram helpers ─────────────────────────────────────────
def _tg_edit(msg_id, text):
    """Edit an existing Telegram message."""
    if not msg_id: return
    token    = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    admin_id = os.getenv("TELEGRAM_ADMIN_ID","").strip()
    if not token or not admin_id: return
    try:
        import requests as r
        r.post(f"https://api.telegram.org/bot{token}/editMessageText",
            json={"chat_id": admin_id, "message_id": msg_id, "text": text, "parse_mode": "HTML"},
            timeout=5)
    except: pass

def _tg_send(text):
    """Send a new Telegram message."""
    token    = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    admin_id = os.getenv("TELEGRAM_ADMIN_ID","").strip()
    if not token or not admin_id: return
    try:
        import requests as r
        r.post(f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": admin_id, "text": text, "parse_mode": "HTML"},
            timeout=5)
    except: pass

# ── Stats ────────────────────────────────────────────────────
@admin_bp.get("/stats")
@jwt_required()
def stats():
    _, err = require_admin()
    if err: return err

    total_users       = User.query.filter_by(role="USER").count()
    total_deposits    = db.session.query(func.sum(Transaction.amount)).filter(Transaction.type=="DEPOSIT", Transaction.status=="COMPLETED", Transaction.balance_type=="main").scalar() or 0
    total_withdrawals = db.session.query(func.sum(func.abs(Transaction.amount))).filter(Transaction.type=="WITHDRAWAL", Transaction.status=="COMPLETED").scalar() or 0
    pending_deposits  = Transaction.query.filter_by(type="DEPOSIT",    status="PENDING", balance_type="main").count()
    pending_withdrawals = Transaction.query.filter_by(type="WITHDRAWAL", status="PENDING").count()
    total_balance     = db.session.query(func.sum(User.balance)).filter_by(role="USER").scalar() or 0
    total_wagered     = db.session.query(func.sum(User.total_wagered)).filter_by(role="USER").scalar() or 0
    week_ago          = datetime.now(timezone.utc) - timedelta(days=7)
    new_users_week    = User.query.filter(User.created_at >= week_ago, User.role=="USER").count()

    return jsonify({
        "totalUsers": total_users, "newUsersWeek": new_users_week,
        "totalDeposits": round(total_deposits,2),
        "totalWithdrawals": round(total_withdrawals,2),
        "pendingDeposits": pending_deposits,
        "pendingWithdrawals": pending_withdrawals,
        "totalUserBalance": round(total_balance,2),
        "totalWagered": round(total_wagered,2),
    })

# ── Pending requests ─────────────────────────────────────────
@admin_bp.get("/pending")
@jwt_required()
def get_pending():
    _, err = require_admin()
    if err: return err

    txns = Transaction.query.filter_by(status="PENDING").filter(
        Transaction.type.in_(["DEPOSIT","WITHDRAWAL"])
    ).order_by(Transaction.created_at.desc()).all()

    result = []
    for t in txns:
        user = User.query.get(t.user_id)
        result.append({
            **t.to_dict(),
            "user": {
                "email": user.email if user else "?",
                "username": user.username if user else "?",
                "firstName": user.first_name if user else "",
                "lastName":  user.last_name  if user else "",
                "balance":   user.balance    if user else 0,
                "withdrawal_bank":    getattr(user,"withdrawal_bank",""),
                "withdrawal_account": getattr(user,"withdrawal_account",""),
                "withdrawal_name":    getattr(user,"withdrawal_name",""),
            },
        })
    return jsonify({"pending": result, "total": len(result)})

# ── Approve / Decline (site → also edits Telegram) ──────────
@admin_bp.post("/transactions/<txn_id>/approve")
@jwt_required()
def approve_txn(txn_id):
    _, err = require_admin()
    if err: return err

    txn  = Transaction.query.get(txn_id)
    if not txn or txn.status != "PENDING":
        return jsonify({"error": "Not found or not pending"}), 404

    user = User.query.get(txn.user_id)

    if txn.type == "DEPOSIT":
        bonus = round(txn.amount * 0.10, 2)
        user.balance       = cap(user.balance + txn.amount)
        user.bonus_balance = round((user.bonus_balance or 0) + bonus, 2)
        txn.status    = "COMPLETED"
        txn.reference = f"Deposit of ₦{txn.amount:,.0f} — approved"
        db.session.add(Transaction(
            user_id=user.id, type="DEPOSIT", amount=bonus,
            reference=f"10% deposit bonus on ₦{txn.amount:,.0f}",
            status="COMPLETED", balance_type="bonus"
        ))
        db.session.commit()
        # Edit Telegram message
        _tg_edit(txn.tg_message_id,
            f"✅ <b>DEPOSIT APPROVED</b> (via dashboard)\n\n"
            f"👤 {user.first_name} {user.last_name} (@{user.username})\n"
            f"💰 ₦{txn.amount:,.2f} + ₦{bonus:,.2f} bonus\n"
            f"📊 New balance: ₦{user.balance:,.2f}"
        )
        # Push notification
        try:
            from app.routes.push import send_push
            send_push(user, "💰 Deposit Approved!", f"₦{txn.amount:,.0f} added to your balance. Bonus: +₦{bonus:,.0f}", "/transactions")
        except: pass

    elif txn.type == "WITHDRAWAL":
        txn.status    = "COMPLETED"
        txn.reference = f"Withdrawal to {getattr(user,'withdrawal_bank','')} — approved"
        db.session.commit()
        _tg_edit(txn.tg_message_id,
            f"✅ <b>WITHDRAWAL APPROVED</b> (via dashboard)\n\n"
            f"👤 {user.first_name} {user.last_name}\n"
            f"🏦 {getattr(user,'withdrawal_bank','')} — {getattr(user,'withdrawal_account','')}\n"
            f"💸 ₦{abs(txn.amount):,.2f}"
        )
        try:
            from app.routes.push import send_push
            send_push(user, "✅ Withdrawal Approved!", f"₦{abs(txn.amount):,.0f} is on its way to your bank.", "/transactions")
        except: pass

    return jsonify({"ok": True, "newBalance": user.balance, "newBonusBalance": user.bonus_balance or 0})


@admin_bp.post("/transactions/<txn_id>/decline")
@jwt_required()
def decline_txn(txn_id):
    _, err = require_admin()
    if err: return err

    txn  = Transaction.query.get(txn_id)
    if not txn or txn.status != "PENDING":
        return jsonify({"error": "Not found or not pending"}), 404

    user = User.query.get(txn.user_id)

    if txn.type == "WITHDRAWAL":
        user.balance = cap(user.balance + abs(txn.amount))
    txn.status    = "FAILED"
    txn.reference = f"{txn.type.title()} of ₦{abs(txn.amount):,.0f} — declined"
    db.session.commit()

    _tg_edit(txn.tg_message_id,
        f"❌ <b>{txn.type} DECLINED</b> (via dashboard)\n\n"
        f"👤 {user.first_name} {user.last_name} (@{user.username})\n"
        f"💸 ₦{abs(txn.amount):,.2f}"
        + (f"\n↩️ Balance refunded" if txn.type == "WITHDRAWAL" else "")
    )
    try:
        from app.routes.push import send_push
        if txn.type == "WITHDRAWAL":
            send_push(user, "❌ Withdrawal Declined", f"₦{abs(txn.amount):,.0f} refunded to your balance.", "/transactions")
        else:
            send_push(user, "❌ Deposit Declined", f"Your deposit was declined. Contact support.", "/transactions")
    except: pass

    return jsonify({"ok": True})

# ── Users ────────────────────────────────────────────────────
@admin_bp.get("/users")
@jwt_required()
def get_users():
    _, err = require_admin()
    if err: return err

    page   = int(request.args.get("page",1))
    limit  = int(request.args.get("limit",20))
    search = request.args.get("search","").strip()

    q = User.query.filter_by(role="USER")
    if search:
        q = q.filter((User.email.ilike(f"%{search}%")) | (User.username.ilike(f"%{search}%")) | (User.first_name.ilike(f"%{search}%")))

    total = q.count()
    users = q.order_by(User.created_at.desc()).offset((page-1)*limit).limit(limit).all()

    return jsonify({
        "users": [{
            "id": u.id, "email": u.email, "username": u.username,
            "firstName": u.first_name, "lastName": u.last_name,
            "balance": u.balance, "bonusBalance": u.bonus_balance or 0,
            "totalWagered": u.total_wagered or 0,
            "isBanned": u.is_banned or False,
            "createdAt": u.created_at.isoformat(),
        } for u in users],
        "total": total, "page": page, "pages": -(-total//limit)
    })


@admin_bp.post("/users/<user_id>/credit")
@jwt_required()
def credit_user(user_id):
    _, err = require_admin()
    if err: return err

    data     = request.get_json()
    amount   = float(data.get("amount",0))
    bal_type = data.get("balanceType","main")
    note     = data.get("note","Admin credit")

    if amount <= 0: return jsonify({"error": "Invalid amount"}), 400
    user = User.query.get(user_id)
    if not user: return jsonify({"error": "User not found"}), 404

    if bal_type == "bonus":
        user.bonus_balance = round((user.bonus_balance or 0) + amount, 2)
    else:
        user.balance = cap(user.balance + amount)

    db.session.add(Transaction(user_id=user_id, type="DEPOSIT", amount=amount,
        reference=f"Admin credit: {note}", status="COMPLETED", balance_type=bal_type))
    db.session.commit()
    _tg_send(f"🔧 <b>Admin Credit</b>\n👤 {user.username} ({user.email})\n💰 +₦{amount:,.0f} → {bal_type}\n📝 {note}")
    return jsonify({"ok": True, "newBalance": user.balance, "newBonusBalance": user.bonus_balance or 0})


@admin_bp.post("/users/<user_id>/ban")
@jwt_required()
def ban_user(user_id):
    _, err = require_admin()
    if err: return err

    user = User.query.get(user_id)
    if not user: return jsonify({"error": "User not found"}), 404
    if user.role == "ADMIN": return jsonify({"error": "Cannot ban admin accounts"}), 400

    user.is_banned = True
    db.session.commit()
    _tg_send(f"🚫 <b>User Banned</b>\n👤 @{user.username} ({user.email})\nBanned by admin.")
    return jsonify({"ok": True})


@admin_bp.post("/users/<user_id>/unban")
@jwt_required()
def unban_user(user_id):
    _, err = require_admin()
    if err: return err

    user = User.query.get(user_id)
    if not user: return jsonify({"error": "User not found"}), 404

    user.is_banned = False
    db.session.commit()
    _tg_send(f"✅ <b>User Unbanned</b>\n👤 @{user.username} ({user.email})\nUnbanned by admin.")
    return jsonify({"ok": True})

# ── All transactions ─────────────────────────────────────────
@admin_bp.get("/transactions")
@jwt_required()
def get_transactions():
    _, err = require_admin()
    if err: return err

    page     = int(request.args.get("page",1))
    limit    = int(request.args.get("limit",30))
    status   = request.args.get("status","")
    txn_type = request.args.get("type","")

    q = Transaction.query
    if status:   q = q.filter_by(status=status.upper())
    if txn_type: q = q.filter_by(type=txn_type.upper())

    total = q.count()
    txns  = q.order_by(Transaction.created_at.desc()).offset((page-1)*limit).limit(limit).all()

    result = []
    for t in txns:
        user = User.query.get(t.user_id)
        result.append({
            **t.to_dict(),
            "user": {"email": user.email if user else "?", "username": user.username if user else "?"},
        })
    return jsonify({"transactions": result, "total": total, "page": page, "pages": -(-total//limit)})

# ── Gift codes ───────────────────────────────────────────────
@admin_bp.get("/gift-codes")
@jwt_required()
def get_gift_codes():
    _, err = require_admin()
    if err: return err
    codes = GiftCode.query.order_by(GiftCode.created_at.desc()).all()
    return jsonify({"codes": [c.to_dict() for c in codes]})

@admin_bp.post("/gift-codes")
@jwt_required()
def create_gift_code():
    _, err = require_admin()
    if err: return err
    data     = request.get_json()
    code     = data.get("code","").strip().upper()
    amount   = float(data.get("amount",0))
    max_uses = int(data.get("maxUses",1))
    bal_type = data.get("balanceType","bonus")
    if not code or amount <= 0: return jsonify({"error": "Code and amount required"}), 400
    if GiftCode.query.filter_by(code=code).first(): return jsonify({"error": "Code already exists"}), 400
    gc = GiftCode(code=code, amount=amount, max_uses=max_uses, balance_type=bal_type)
    db.session.add(gc)
    db.session.commit()
    return jsonify({"ok": True, "code": gc.to_dict()}), 201

@admin_bp.delete("/gift-codes/<code_id>")
@jwt_required()
def delete_gift_code(code_id):
    _, err = require_admin()
    if err: return err
    gc = GiftCode.query.get(code_id)
    if not gc: return jsonify({"error": "Not found"}), 404
    gc.is_active = False
    db.session.commit()
    return jsonify({"ok": True})
