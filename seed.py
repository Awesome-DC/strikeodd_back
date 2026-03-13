import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timezone, timedelta
from app import create_app
from app.models import db, User, Sport, Event, Odd, Transaction
import bcrypt

app = create_app()

with app.app_context():
    db.create_all()

    # Sports
    sports_data = [
        ("Football", "football", "⚽"),
        ("Basketball", "basketball", "🏀"),
        ("Tennis", "tennis", "🎾"),
        ("Cricket", "cricket", "🏏"),
        ("Boxing", "boxing", "🥊"),
    ]
    sports = {}
    for name, slug, icon in sports_data:
        s = Sport.query.filter_by(slug=slug).first()
        if not s:
            s = Sport(name=name, slug=slug, icon=icon)
            db.session.add(s)
            db.session.flush()
        sports[slug] = s

    now = datetime.now(timezone.utc)

    # Events
    events_data = [
        {"sport": "football", "home": "Manchester City", "away": "Arsenal",      "time": now + timedelta(hours=2),  "status": "UPCOMING", "league": "Premier League"},
        {"sport": "football", "home": "Real Madrid",      "away": "Barcelona",   "time": now + timedelta(hours=4),  "status": "UPCOMING", "league": "La Liga"},
        {"sport": "football", "home": "PSG",              "away": "Bayern",      "time": now - timedelta(minutes=30), "status": "LIVE",   "league": "Champions League", "hs": 1, "as": 0},
        {"sport": "basketball","home": "LA Lakers",       "away": "Golden State","time": now + timedelta(hours=6),  "status": "UPCOMING", "league": "NBA"},
        {"sport": "basketball","home": "Boston Celtics",  "away": "Miami Heat",  "time": now - timedelta(minutes=45), "status": "LIVE",   "league": "NBA", "hs": 67, "as": 54},
    ]

    for ed in events_data:
        e = Event(
            sport_id=sports[ed["sport"]].id,
            home_team=ed["home"], away_team=ed["away"],
            start_time=ed["time"].replace(tzinfo=None),
            status=ed["status"], league=ed["league"],
            home_score=ed.get("hs"), away_score=ed.get("as")
        )
        db.session.add(e)
        db.session.flush()

        if ed["sport"] == "football":
            odds = [
                ("1X2", "Home", 1.75), ("1X2", "Draw", 3.20), ("1X2", "Away", 4.50),
                ("BTTS", "Yes", 1.65), ("BTTS", "No", 2.10),
                ("Over/Under", "Over 2.5", 1.85), ("Over/Under", "Under 2.5", 1.90),
            ]
        else:
            odds = [
                ("Moneyline", "Home", 1.60), ("Moneyline", "Away", 2.30),
                ("Over/Under", "Over 210.5", 1.87), ("Over/Under", "Under 210.5", 1.87),
            ]

        for market, selection, value in odds:
            db.session.add(Odd(event_id=e.id, market=market, selection=selection, value=value))

    # Demo user
    if not User.query.filter_by(email="demo@strikeodds.com").first():
        hashed = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
        user = User(
            email="demo@strikeodds.com", username="demo_user",
            password=hashed, first_name="Demo", last_name="User", balance=1000
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(Transaction(user_id=user.id, type="DEPOSIT", amount=1000, reference="Welcome bonus"))

    db.session.commit()
    print("✅ Database seeded!")
    print("📧 Demo login: demo@strikeodds.com / password123")
