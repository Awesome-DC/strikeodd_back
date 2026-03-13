"""
migrate.py — works for both local SQLite and Render PostgreSQL.
Run: python migrate.py
"""
import os
from app import create_app
from app.models import db

app = create_app()

with app.app_context():
    db_url = app.config["SQLALCHEMY_DATABASE_URI"]
    is_postgres = "postgresql" in db_url

    if is_postgres:
        # PostgreSQL — use SQLAlchemy text() to run raw SQL safely
        from sqlalchemy import text, inspect

        with db.engine.connect() as conn:
            inspector = inspect(db.engine)

            # Users table — add missing columns
            user_cols = [c["name"] for c in inspector.get_columns("users")]
            for col, typ in [
                ("withdrawal_bank",    "TEXT"),
                ("withdrawal_account", "TEXT"),
                ("withdrawal_name",    "TEXT"),
                ("withdrawal_pin",     "TEXT"),
            ]:
                if col not in user_cols:
                    conn.execute(text(f'ALTER TABLE users ADD COLUMN {col} {typ}'))
                    print(f"  ✅ users.{col}")

            # Transactions table
            txn_cols = [c["name"] for c in inspector.get_columns("transactions")]
            if "status" not in txn_cols:
                conn.execute(text("ALTER TABLE transactions ADD COLUMN status TEXT DEFAULT 'PENDING'"))
                print("  ✅ transactions.status")

            conn.commit()

    else:
        # SQLite — original approach
        import sqlite3
        paths = [
            os.path.join(os.path.dirname(__file__), "strikeodds.db"),
            os.path.join(os.path.dirname(__file__), "instance", "strikeodds.db"),
        ]
        db_path = next((p for p in paths if os.path.exists(p)), paths[0])
        print(f"Migrating SQLite: {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        user_cols = [r[1] for r in cursor.fetchall()]
        cursor.execute("PRAGMA table_info(transactions)")
        txn_cols = [r[1] for r in cursor.fetchall()]
        for col, typ in [("withdrawal_bank","TEXT"),("withdrawal_account","TEXT"),("withdrawal_name","TEXT"),("withdrawal_pin","TEXT")]:
            if col not in user_cols:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
                print(f"  ✅ users.{col}")
        if "status" not in txn_cols:
            cursor.execute("ALTER TABLE transactions ADD COLUMN status TEXT DEFAULT 'PENDING'")
            print("  ✅ transactions.status")
        conn.commit()
        conn.close()

    print("\n✅ Migration complete!")
