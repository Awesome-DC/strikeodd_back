from flask import Flask
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
from app.routes.withdraw import withdraw_bp
from app.routes.deposit import deposit_bp
from app.routes.crash import crash_bp
from app.crash_engine import engine as crash_engine  # starts engine thread

load_dotenv()

def get_database_url():
    url = os.getenv("DATABASE_URL", "")
    if not url:
        # Local fallback — SQLite
        base_dir = os.path.abspath(os.path.dirname(__file__))
        db_path = os.path.join(base_dir, '..', 'strikeodds.db')
        return f"sqlite:///{db_path}"
    # Render (and older Heroku) give postgres:// — SQLAlchemy needs postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url

def create_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = get_database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,       # drop stale connections automatically
        "pool_recycle": 300,         # recycle connections every 5 min
        "connect_args": {} if get_database_url().startswith("sqlite") else {
            "sslmode": "require"     # Render requires SSL for Postgres
        }
    }
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")

    # Extensions
    db.init_app(app)
    Migrate(app, db)
    JWTManager(app)
    client_url = os.getenv("CLIENT_URL", "http://localhost:5173").strip().rstrip("/")
    CORS(app,
         origins=[client_url, "http://localhost:5173", "http://localhost:3000"],
         supports_credentials=True,
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    )

    # Register blueprints
    app.register_blueprint(auth_bp,     url_prefix="/api/auth")
    app.register_blueprint(events_bp,   url_prefix="/api/events")
    app.register_blueprint(bets_bp,     url_prefix="/api/bets")
    app.register_blueprint(users_bp,    url_prefix="/api/users")
    app.register_blueprint(sports_bp,   url_prefix="/api/sports")
    app.register_blueprint(withdraw_bp, url_prefix="/api/withdraw")
    app.register_blueprint(deposit_bp,  url_prefix="/api/deposit")
    app.register_blueprint(crash_bp,    url_prefix="/api/crash")

    # Handle preflight OPTIONS requests globally
    @app.before_request
    def handle_options():
        from flask import request, Response
        if request.method == "OPTIONS":
            res = Response()
            res.headers["Access-Control-Allow-Origin"] = "*"
            res.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            res.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            return res, 200

    # Health check
    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app
