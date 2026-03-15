from flask import Flask, request, Response, jsonify
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
from app.routes.withdraw import withdraw_bp
from app.routes.deposit import deposit_bp
from app.routes.crash import crash_bp
from app.routes.referral import referral_bp
from app.routes.giftcode import giftcode_bp
from app.routes.push import push_bp
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

    # ── Run migrations immediately on startup ──
    with app.app_context():
        db.create_all()
        try:
            from sqlalchemy import text, inspect
            with db.engine.connect() as conn:
                inspector = inspect(db.engine)
                existing_cols = [c["name"] for c in inspector.get_columns("users")]

                all_user_cols = [
                    ("bonus_balance",      "FLOAT DEFAULT 0"),
                    ("ref_code",           "VARCHAR(20)"),
                    ("referred_by",        "VARCHAR"),
                    ("total_wagered",      "FLOAT DEFAULT 0"),
                    ("push_subscription",  "TEXT"),
                ]
                for col, typ in all_user_cols:
                    if col not in existing_cols:
                        try:
                            conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {typ}"))
                            conn.commit()
                            print(f"✅ Added users.{col}")
                        except Exception as ex:
                            conn.rollback()
                            print(f"  skip users.{col}: {ex}")

                # transactions.balance_type
                txn_cols = [c["name"] for c in inspector.get_columns("transactions")]
                if "balance_type" not in txn_cols:
                    try:
                        conn.execute(text("ALTER TABLE transactions ADD COLUMN balance_type VARCHAR(10) DEFAULT 'main'"))
                        conn.commit()
                        print("✅ Added transactions.balance_type")
                    except Exception as ex:
                        conn.rollback()
                        print(f"  skip balance_type: {ex}")
        except Exception as e:
            print(f"Migration note: {e}")

    # ── Manual CORS ──
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

    # ── Blueprints ──
    app.register_blueprint(auth_bp,     url_prefix="/api/auth")
    app.register_blueprint(events_bp,   url_prefix="/api/events")
    app.register_blueprint(bets_bp,     url_prefix="/api/bets")
    app.register_blueprint(users_bp,    url_prefix="/api/users")
    app.register_blueprint(sports_bp,   url_prefix="/api/sports")
    app.register_blueprint(withdraw_bp, url_prefix="/api/withdraw")
    app.register_blueprint(deposit_bp,  url_prefix="/api/deposit")
    app.register_blueprint(crash_bp,      url_prefix="/api/crash")
    app.register_blueprint(referral_bp,   url_prefix="/api/referral")
    app.register_blueprint(giftcode_bp,   url_prefix="/api/giftcode")
    app.register_blueprint(push_bp,       url_prefix="/api/push")



    # ── Unified Telegram webhook (deposit + withdrawal callbacks) ──
    @app.post("/api/telegram-webhook")
    def unified_tg_webhook():
        from app.routes.deposit import telegram_webhook as dep_hook
        from app.routes.withdraw import withdrawal_telegram_webhook as wd_hook
        data    = request.get_json(silent=True) or {}
        cb      = data.get("callback_query", {})
        cb_data = cb.get("data", "")
        # Withdrawal callbacks start with w (wapprove_ / wdecline_)
        if cb_data.startswith("w"):
            return wd_hook()
        # Deposit callbacks (approve_ / decline_)
        return dep_hook()

    # ── Register webhook with Telegram ──
    @app.get("/api/setup-webhook")
    def setup_webhook():
        """Visit once after deploy: GET /api/setup-webhook"""
        try:
            import requests as r
        except ImportError:
            return jsonify({"error": "requests not installed"}), 500
        token    = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        base_url = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
        if not base_url:
            # Try to build from Railway domain
            domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
            if domain:
                base_url = f"https://{domain}"
        if not base_url:
            return jsonify({"error": "Set PUBLIC_URL env var to your Railway backend URL e.g. https://strikeoddback-production.up.railway.app"}), 400
        webhook_url = f"{base_url}/api/telegram-webhook"
        resp = r.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "allowed_updates": ["callback_query", "message"]},
            timeout=10
        )
        return jsonify({"webhook_url": webhook_url, "telegram": resp.json()})

    # ── Health check ──
    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app
