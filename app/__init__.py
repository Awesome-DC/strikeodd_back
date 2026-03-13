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

def create_app():
    app = Flask(__name__)

    # SQLite config — file will be created automatically in backend folder
    base_dir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(base_dir, '..', 'strikeodds.db')
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", f"sqlite:///{db_path}")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")

    # Extensions
    db.init_app(app)
    Migrate(app, db)
    JWTManager(app)
    CORS(app, origins=[os.getenv("CLIENT_URL", "http://localhost:5173")], supports_credentials=True)

    # Register blueprints
    app.register_blueprint(auth_bp,   url_prefix="/api/auth")
    app.register_blueprint(events_bp, url_prefix="/api/events")
    app.register_blueprint(bets_bp,   url_prefix="/api/bets")
    app.register_blueprint(users_bp,  url_prefix="/api/users")
    app.register_blueprint(sports_bp, url_prefix="/api/sports")
    app.register_blueprint(withdraw_bp, url_prefix="/api/withdraw")
    app.register_blueprint(deposit_bp, url_prefix="/api/deposit")
    app.register_blueprint(crash_bp,   url_prefix="/api/crash")

    # Health check
    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app
