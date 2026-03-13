"""Run once to apply new DB columns."""
import sqlite3, os

paths = [
    os.path.join(os.path.dirname(__file__), "strikeodds.db"),
    os.path.join(os.path.dirname(__file__), "instance", "strikeodds.db"),
]
db_path = next((p for p in paths if os.path.exists(p)), paths[0])
print(f"Migrating: {db_path}")

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
print("\n✅ Migration complete! Restart Flask.")
