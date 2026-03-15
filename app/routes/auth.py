from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
import bcrypt, random, string

from app.models import db, User, Transaction, cap

auth_bp = Blueprint("auth", __name__)

def gen_ref_code():
    """Generate unique 8-char ref code."""
    chars = string.ascii_uppercase + string.digits
    while True:
        code = "SO" + "".join(random.choices(chars, k=6))
        if not User.query.filter_by(ref_code=code).first():
            return code

@auth_bp.post("/register")
def register():
    data = request.get_json()
    required = ["email", "username", "password", "firstName", "lastName"]
    if not all(data.get(f) for f in required):
        return jsonify({"error": "All fields are required"}), 400

    if User.query.filter((User.email == data["email"]) | (User.username == data["username"])).first():
        return jsonify({"error": "Email or username already taken"}), 409

    hashed = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()

    # Check referral code
    ref_code = data.get("refCode", "").strip().upper()
    referrer = None
    if ref_code:
        referrer = User.query.filter_by(ref_code=ref_code).first()

    user = User(
        email=data["email"], username=data["username"], password=hashed,
        first_name=data["firstName"], last_name=data["lastName"],
        balance=0.0,          # real money starts at 0
        bonus_balance=1000.0, # ₦1000 welcome bonus → bonus balance
        ref_code=gen_ref_code(),
        referred_by=referrer.id if referrer else None,
    )
    db.session.add(user)
    db.session.flush()

    # Welcome bonus transaction (bonus balance)
    db.session.add(Transaction(
        user_id=user.id, type="DEPOSIT", amount=1000,
        reference="Welcome bonus", status="COMPLETED", balance_type="bonus"
    ))

    # Reward referrer ₦200 to their bonus balance
    if referrer:
        referrer.bonus_balance = cap(referrer.bonus_balance + 200)
        db.session.add(Transaction(
            user_id=referrer.id, type="REFERRAL", amount=200,
            reference=f"Referral reward — {user.username} joined",
            status="COMPLETED", balance_type="bonus"
        ))

    db.session.commit()
    token = create_access_token(identity=user.id)
    return jsonify({"token": token, "user": user.to_dict()}), 201


@auth_bp.post("/login")
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data.get("email")).first()
    if not user or not bcrypt.checkpw(data.get("password", "").encode(), user.password.encode()):
        return jsonify({"error": "Invalid credentials"}), 401
    if user.is_banned:
        return jsonify({"error": "ACCOUNT_BANNED"}), 403
    token = create_access_token(identity=user.id)
    return jsonify({"token": token, "user": user.to_dict()})


@auth_bp.get("/me")
@jwt_required()
def me():
    user = User.query.get(get_jwt_identity())
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.is_banned:
        return jsonify({"error": "ACCOUNT_BANNED"}), 403
    return jsonify({"user": user.to_dict()})
