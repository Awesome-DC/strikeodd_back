from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User, Transaction, GiftCode, cap
from datetime import datetime, timezone, timedelta
from sqlalchemy import func
import bcrypt

admin_bp = Blueprint("admin", __name__)

def require_admin():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or user.role != "ADMIN":
        return None, (jsonify({"error": "Admin access required"}), 403)
    return user, None

# ── Stats overview ──────────────────────────────────────────
@admin_bp.get("/stats")
@jwt_required()
def stats():
    _, err = require_admin(); 
    if err: return err

    total_users    = User.query.filter_by(role="USER").count()
    total_deposits = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.type=="DEPOSIT", Transaction.status=="COMPLETED",
        Transaction.balance_type=="main"
    ).scalar() or 0
    total_withdrawals = db.session.query(func.sum(func.abs(Transaction.amount))).filter(
        Transaction.type=="WITHDRAWAL", Transaction.status=="COMPLETED"
    ).scalar() or 0
    pending_deposits = Transaction.query.filter_by(type="DEPOSIT", status="PENDING", balance_type="main").count()
    pending_withdrawals = Transaction.query.filter_by(type="WITHDRAWAL", status="PENDING").count()
    total_balance = db.session.query(func.sum(User.balance)).filter_by(role="USER").scalar() or 0
    total_wagered = db.session.query(func.sum(User.total_wagered)).filter_by(role="USER").scalar() or 0

    # New users last 7 days
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    new_users_week = User.query.filter(User.created_at >= week_ago, User.role=="USER").count()

    return jsonify({
        "totalUsers": total_users,
        "newUsersWeek": new_users_week,
        "totalDeposits": round(total_deposits, 2),
        "totalWithdrawals": round(total_withdrawals, 2),
        "pendingDeposits": pending_deposits,
        "pendingWithdrawals": pending_withdrawals,
        "totalUserBalance": round(total_balance, 2),
        "totalWagered": round(total_wagered, 2),
        "houseEdge": round(total_wagered * 0.03, 2),  # estimated
    })

# ── Users ───────────────────────────────────────────────────
@admin_bp.get("/users")
@jwt_required()
def get_users():
    _, err = require_admin()
    if err: return err

    page    = int(request.args.get("page", 1))
    limit   = int(request.args.get("limit", 20))
    search  = request.args.get("search", "").strip()

    q = User.query.filter_by(role="USER")
    if search:
        q = q.filter(
            (User.email.ilike(f"%{search}%")) |
            (User.username.ilike(f"%{search}%")) |
            (User.first_name.ilike(f"%{search}%"))
        )
    total = q.count()
    users = q.order_by(User.created_at.desc()).offset((page-1)*limit).limit(limit).all()

    return jsonify({
        "users": [{
            "id": u.id, "email": u.email, "username": u.username,
            "firstName": u.first_name, "lastName": u.last_name,
            "balance": u.balance, "bonusBalance": u.bonus_balance or 0,
            "totalWagered": u.total_wagered or 0,
            "createdAt": u.created_at.isoformat(),
        } for u in users],
        "total": total, "page": page, "pages": -(-total // limit)
    })

@admin_bp.post("/users/<user_id>/credit")
@jwt_required()
def credit_user(user_id):
    _, err = require_admin()
    if err: return err

    data   = request.get_json()
    amount = float(data.get("amount", 0))
    bal_type = data.get("balanceType", "main")
    note   = data.get("note", "Admin credit")

    if amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if bal_type == "bonus":
        user.bonus_balance = round((user.bonus_balance or 0) + amount, 2)
    else:
        user.balance = cap(user.balance + amount)

    db.session.add(Transaction(
        user_id=user_id, type="DEPOSIT", amount=amount,
        reference=f"Admin credit: {note}",
        status="COMPLETED", balance_type=bal_type
    ))
    db.session.commit()
    return jsonify({"ok": True, "newBalance": user.balance, "newBonusBalance": user.bonus_balance})

@admin_bp.post("/users/<user_id>/debit")
@jwt_required()
def debit_user(user_id):
    _, err = require_admin()
    if err: return err

    data   = request.get_json()
    amount = float(data.get("amount", 0))
    note   = data.get("note", "Admin debit")

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if amount > user.balance:
        return jsonify({"error": "Insufficient balance"}), 400

    user.balance = round(user.balance - amount, 2)
    db.session.add(Transaction(
        user_id=user_id, type="WITHDRAWAL", amount=-amount,
        reference=f"Admin debit: {note}",
        status="COMPLETED", balance_type="main"
    ))
    db.session.commit()
    return jsonify({"ok": True, "newBalance": user.balance})

# ── Transactions ────────────────────────────────────────────
@admin_bp.get("/transactions")
@jwt_required()
def get_transactions():
    _, err = require_admin()
    if err: return err

    page   = int(request.args.get("page", 1))
    limit  = int(request.args.get("limit", 30))
    status = request.args.get("status", "")
    txn_type = request.args.get("type", "")

    q = Transaction.query
    if status: q = q.filter_by(status=status.upper())
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

    return jsonify({"transactions": result, "total": total, "page": page, "pages": -(-total // limit)})

@admin_bp.post("/transactions/<txn_id>/approve")
@jwt_required()
def approve_txn(txn_id):
    _, err = require_admin()
    if err: return err

    txn = Transaction.query.get(txn_id)
    if not txn or txn.status != "PENDING":
        return jsonify({"error": "Transaction not found or not pending"}), 404

    user = User.query.get(txn.user_id)
    if txn.type == "DEPOSIT":
        bonus = round(txn.amount * 0.10, 2)
        user.balance = cap(user.balance + txn.amount)
        user.bonus_balance = round((user.bonus_balance or 0) + bonus, 2)
        txn.status = "COMPLETED"
        db.session.add(Transaction(
            user_id=user.id, type="DEPOSIT", amount=bonus,
            reference=f"10% deposit bonus on ₦{txn.amount:,.0f}",
            status="COMPLETED", balance_type="bonus"
        ))
    elif txn.type == "WITHDRAWAL":
        txn.status = "COMPLETED"
    db.session.commit()
    return jsonify({"ok": True})

@admin_bp.post("/transactions/<txn_id>/decline")
@jwt_required()
def decline_txn(txn_id):
    _, err = require_admin()
    if err: return err

    txn = Transaction.query.get(txn_id)
    if not txn or txn.status != "PENDING":
        return jsonify({"error": "Transaction not found or not pending"}), 404

    user = User.query.get(txn.user_id)
    if txn.type == "WITHDRAWAL":
        user.balance = cap(user.balance + abs(txn.amount))
    txn.status = "FAILED"
    db.session.commit()
    return jsonify({"ok": True})

# ── Gift Codes ──────────────────────────────────────────────
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
    amount   = float(data.get("amount", 0))
    max_uses = int(data.get("maxUses", 1))
    bal_type = data.get("balanceType", "bonus")

    if not code or amount <= 0:
        return jsonify({"error": "Code and amount required"}), 400
    if GiftCode.query.filter_by(code=code).first():
        return jsonify({"error": "Code already exists"}), 400

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
