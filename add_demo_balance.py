"""
DEV TOOL — Add balance to any account for testing.
Usage:
  py add_demo_balance.py                        # adds 10,000 to demo account
  py add_demo_balance.py 50000                  # adds 50,000 to demo account
  py add_demo_balance.py 10000 user@email.com   # adds to specific account

This script is STANDALONE — does not affect any app logic.
"""
import sys, os, sqlite3

AMOUNT = float(sys.argv[1]) if len(sys.argv) > 1 else 10000.0
EMAIL  = sys.argv[2] if len(sys.argv) > 2 else "demo@strikeodds.com"

# Find DB
paths = [
    os.path.join(os.path.dirname(__file__), "strikeodds.db"),
    os.path.join(os.path.dirname(__file__), "instance", "strikeodds.db"),
]
db_path = next((p for p in paths if os.path.exists(p)), None)
if not db_path:
    print("❌ Database not found. Make sure you've run the app at least once.")
    sys.exit(1)

conn   = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT id, email, first_name, last_name, balance FROM users WHERE email = ?", (EMAIL,))
user = cursor.fetchone()

if not user:
    print(f"❌ No user found with email: {EMAIL}")
    print("\nAvailable accounts:")
    cursor.execute("SELECT email, first_name, balance FROM users")
    for row in cursor.fetchall():
        print(f"  • {row[0]} ({row[1]}) — ₦{row[2]:,.2f}")
    conn.close()
    sys.exit(1)

uid, email, fname, lname, old_bal = user
new_bal = old_bal + AMOUNT

cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (new_bal, uid))
cursor.execute(
    "INSERT INTO transactions (id, user_id, type, amount, reference, status, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
    (f"dev_{os.urandom(4).hex()}", uid, "DEPOSIT", AMOUNT, f"Dev top-up via add_demo_balance.py", "COMPLETED")
)
conn.commit()
conn.close()

print(f"\n✅ Done!")
print(f"   User    : {fname} {lname} ({email})")
print(f"   Added   : ₦{AMOUNT:,.2f}")
print(f"   Old bal : ₦{old_bal:,.2f}")
print(f"   New bal : ₦{new_bal:,.2f}")
print(f"\nRefresh the app to see updated balance.")
