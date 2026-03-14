from flask import Flask, request, Response
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from dotenv import load_dotenv
import os

from app.models import db
from app.routes.auth import auth_bp
from app.routes.events import events_bp
from app.routes.bets import bets_bp
from app.routes.users import users_bp
from app.routes.sports import sports_bp
from app.routes.withdraw import withdraw_bp, withdrawal_telegram_webhook
from app.routes.deposit import deposit_bp
from app.routes.crash import crash_bp
from app.crash_engine import engine as crash_engine

load_dotenv()

def get_database_url():
    url = os.getenv("DATABASE_URL", "")
    if not url:
        base_dir = os.path.abspath(os.path.dirname(__file__))
        db_path = os.path.join(base_dir, '..', 'strikeodds.db')
        return f"sqlite:///{db_path}"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url

def create_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = get_database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me-32-chars-min")

    db.init_app(app)
    Migrate(app, db)
    JWTManager(app)

    client_url = os.getenv("CLIENT_URL", "http://localhost:5173").strip().rstrip("/")

    # Manual CORS — bulletproof, handles all cases
    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            response = Response()
            response.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "*")
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            return response, 200

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin", "")
        response.headers["Access-Control-Allow-Origin"] = origin if origin else "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return response

    # Register blueprints
    app.register_blueprint(auth_bp,     url_prefix="/api/auth")
    app.register_blueprint(events_bp,   url_prefix="/api/events")
    app.register_blueprint(bets_bp,     url_prefix="/api/bets")
    app.register_blueprint(users_bp,    url_prefix="/api/users")
    app.register_blueprint(sports_bp,   url_prefix="/api/sports")
    app.register_blueprint(withdraw_bp, url_prefix="/api/withdraw")
    app.register_blueprint(deposit_bp,  url_prefix="/api/deposit")
    app.register_blueprint(crash_bp,    url_prefix="/api/crash")

    # Auto-create all tables on startup
    with app.app_context():
        db.create_all()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/setup-webhook")
    def setup_webhook():
        """Call this once to register Telegram webhook: GET /api/setup-webhook"""
        import os
        try:
            import requests as r
        except ImportError:
            return {"error": "requests not installed"}, 500
        token    = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
        base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("PUBLIC_URL","")
        if not base_url:
            return {"error": "Set RAILWAY_PUBLIC_DOMAIN or PUBLIC_URL env var"}, 400
        if not base_url.startswith("http"):
            base_url = f"https://{base_url}"
        webhook_url = f"{base_url}/api/telegram-webhook"
        resp = r.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url},
            timeout=10
        )
        return resp.json()

    return app
