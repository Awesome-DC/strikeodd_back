from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
import bcrypt

from app.models import db, User, Transaction

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
def register():
    data = request.get_json()
    required = ["email", "username", "password", "firstName", "lastName"]
    if not all(data.get(f) for f in required):
        return jsonify({"error": "All fields are required"}), 400

    if User.query.filter((User.email == data["email"]) | (User.username == data["username"])).first():
        return jsonify({"error": "Email or username already taken"}), 409

    hashed = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()

    user = User(
        email=data["email"], username=data["username"], password=hashed,
        first_name=data["firstName"], last_name=data["lastName"]
    )
    db.session.add(user)
    db.session.flush()

    # Welcome bonus transaction
    db.session.add(Transaction(user_id=user.id, type="DEPOSIT", amount=1000, reference="Welcome bonus"))
    db.session.commit()

    token = create_access_token(identity=user.id)
    return jsonify({"token": token, "user": user.to_dict()}), 201


@auth_bp.post("/login")
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data.get("email")).first()

    if not user or not bcrypt.checkpw(data.get("password", "").encode(), user.password.encode()):
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_access_token(identity=user.id)
    return jsonify({"token": token, "user": user.to_dict()})


@auth_bp.get("/me")
@jwt_required()
def me():
    user = User.query.get(get_jwt_identity())
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user": user.to_dict()})
