from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import uuid

db = SQLAlchemy()

MAX_BALANCE = 200_000_000.0  # ₦200,000,000 hard cap

def gen_id():
    return str(uuid.uuid4())

def cap(val):
    """Clamp balance to max cap."""
    return min(round(val, 2), MAX_BALANCE)

class User(db.Model):
    __tablename__ = "users"
    id         = db.Column(db.String, primary_key=True, default=gen_id)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    username   = db.Column(db.String(40),  unique=True, nullable=False)
    password   = db.Column(db.String(200), nullable=False)
    first_name = db.Column(db.String(80),  nullable=False)
    last_name  = db.Column(db.String(80),  nullable=False)

    # Real money — deposits go here
    balance        = db.Column(db.Float, default=0.0)
    # Bonus money — register bonus + referral rewards go here
    bonus_balance  = db.Column(db.Float, default=0.0)

    role       = db.Column(db.String(10), default="USER")
    withdrawal_bank    = db.Column(db.String(100))
    withdrawal_account = db.Column(db.String(20))
    withdrawal_name    = db.Column(db.String(120))
    withdrawal_pin     = db.Column(db.String(10))

    # Referral
    ref_code      = db.Column(db.String(20), unique=True)
    referred_by   = db.Column(db.String, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    bets         = db.relationship("Bet", backref="user", lazy=True)
    transactions = db.relationship("Transaction", backref="user", lazy=True)
    referrals    = db.relationship("User", foreign_keys=[referred_by], lazy=True)

    def to_dict(self):
        return {
            "id": self.id, "email": self.email, "username": self.username,
            "firstName": self.first_name, "lastName": self.last_name,
            "balance": self.balance,
            "bonusBalance": self.bonus_balance,
            "role": self.role,
            "refCode": self.ref_code,
            "referralCount": len(self.referrals) if self.referrals else 0,
        }


class Sport(db.Model):
    __tablename__ = "sports"
    id        = db.Column(db.String, primary_key=True, default=gen_id)
    name      = db.Column(db.String(50), unique=True, nullable=False)
    slug      = db.Column(db.String(50), unique=True, nullable=False)
    icon      = db.Column(db.String(10))
    is_active = db.Column(db.Boolean, default=True)
    events    = db.relationship("Event", backref="sport", lazy=True)
    def to_dict(self):
        return {"id": self.id, "name": self.name, "slug": self.slug, "icon": self.icon}


class Event(db.Model):
    __tablename__ = "events"
    id         = db.Column(db.String, primary_key=True, default=gen_id)
    sport_id   = db.Column(db.String, db.ForeignKey("sports.id"), nullable=False)
    home_team  = db.Column(db.String(100), nullable=False)
    away_team  = db.Column(db.String(100), nullable=False)
    home_score = db.Column(db.Integer)
    away_score = db.Column(db.Integer)
    start_time = db.Column(db.DateTime, nullable=False)
    status     = db.Column(db.String(20), default="UPCOMING")
    league     = db.Column(db.String(100))
    country    = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    odds = db.relationship("Odd", backref="event", lazy=True)
    bets = db.relationship("Bet", backref="event", lazy=True)
    def to_dict(self):
        return {
            "id": self.id, "homeTeam": self.home_team, "awayTeam": self.away_team,
            "homeScore": self.home_score, "awayScore": self.away_score,
            "startTime": self.start_time.isoformat(),
            "status": self.status, "league": self.league, "country": self.country,
            "sport": self.sport.to_dict(),
            "odds": [o.to_dict() for o in self.odds if o.is_active],
        }


class Odd(db.Model):
    __tablename__ = "odds"
    id         = db.Column(db.String, primary_key=True, default=gen_id)
    event_id   = db.Column(db.String, db.ForeignKey("events.id"), nullable=False)
    market     = db.Column(db.String(50))
    selection  = db.Column(db.String(50))
    value      = db.Column(db.Float, nullable=False)
    is_active  = db.Column(db.Boolean, default=True)
    def to_dict(self):
        return {"id": self.id, "market": self.market, "selection": self.selection, "value": self.value}


class Bet(db.Model):
    __tablename__ = "bets"
    id         = db.Column(db.String, primary_key=True, default=gen_id)
    user_id    = db.Column(db.String, db.ForeignKey("users.id"), nullable=False)
    event_id   = db.Column(db.String, db.ForeignKey("events.id"))
    type       = db.Column(db.String(20), default="SINGLE")
    stake      = db.Column(db.Float, nullable=False)
    total_odds = db.Column(db.Float, nullable=False)
    potential  = db.Column(db.Float, nullable=False)
    status     = db.Column(db.String(20), default="PENDING")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    legs       = db.relationship("BetLeg", backref="bet", lazy=True)
    def to_dict(self):
        return {
            "id": self.id, "type": self.type, "stake": self.stake,
            "totalOdds": self.total_odds, "potential": self.potential,
            "status": self.status, "createdAt": self.created_at.isoformat(),
            "legs": [l.to_dict() for l in self.legs],
        }


class BetLeg(db.Model):
    __tablename__ = "bet_legs"
    id        = db.Column(db.String, primary_key=True, default=gen_id)
    bet_id    = db.Column(db.String, db.ForeignKey("bets.id"), nullable=False)
    odd_id    = db.Column(db.String, db.ForeignKey("odds.id"), nullable=False)
    odd_value = db.Column(db.Float, nullable=False)
    odd       = db.relationship("Odd")
    def to_dict(self):
        return {"oddId": self.odd_id, "oddValue": self.odd_value, "odd": self.odd.to_dict()}


class Transaction(db.Model):
    __tablename__ = "transactions"
    id         = db.Column(db.String, primary_key=True, default=gen_id)
    user_id    = db.Column(db.String, db.ForeignKey("users.id"), nullable=False)
    type       = db.Column(db.String(30), nullable=False)
    amount     = db.Column(db.Float, nullable=False)
    reference  = db.Column(db.String(200))
    status     = db.Column(db.String(20), default="PENDING")
    balance_type = db.Column(db.String(10), default="main")  # "main" or "bonus"
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    def to_dict(self):
        return {
            "id": self.id, "type": self.type, "amount": self.amount,
            "reference": self.reference, "status": self.status,
            "balanceType": self.balance_type,
            "createdAt": self.created_at.isoformat(),
        }
