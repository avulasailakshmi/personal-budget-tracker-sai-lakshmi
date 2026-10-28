import csv
import hashlib
import io
import os
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "development-only-key"),
        DATABASE=os.getenv("DATABASE_PATH", str(BASE_DIR / "budget_tracker.db")),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    def db():
        connection = sqlite3.connect(app.config["DATABASE"])
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def init_db():
        with db() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL CHECK(type IN ('cash','bank','card')),
                    opening_balance REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL CHECK(type IN ('income','expense','transfer_in','transfer_out')),
                    amount REAL NOT NULL CHECK(amount > 0),
                    transaction_date TEXT NOT NULL,
                    category TEXT NOT NULL,
                    account_id INTEGER NOT NULL,
                    note TEXT DEFAULT '',
                    transfer_group TEXT,
                    import_hash TEXT UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS budgets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    month TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount REAL NOT NULL CHECK(amount > 0),
                    UNIQUE(month, category)
                );
                """
            )

    def error(message, status=400, details=None):
        payload = {"error": message}
        if details is not None:
            payload["details"] = details
        return jsonify(payload), status

    def valid_date(value):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    def valid_month(value):
        try:
            datetime.strptime(value, "%Y-%m")
            return True
        except (TypeError, ValueError):
            return False

    def account_exists(conn, account_id):
        return conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone() is not None

    def transaction_payload(data, allow_transfer=False):
        tx_type = str(data.get("type", "")).strip()
        allowed = {"income", "expense"}
        if allow_transfer:
            allowed |= {"transfer_in", "transfer_out"}
        if tx_type not in allowed:
            return None, "Type must be income or expense."
        try:
            amount = round(float(data.get("amount", 0)), 2)
        except (TypeError, ValueError):
            return None, "Amount must be a number."
        if amount <= 0:
            return None, "Amount must be greater than zero."
        tx_date = str(data.get("date", "")).strip()
        if not valid_date(tx_date):
            return None, "Date must use YYYY-MM-DD format."
        category = str(data.get("category", "")).strip()
        if not category:
            return None, "Category is required."
        try:
            account_id = int(data.get("account_id"))
        except (TypeError, ValueError):
            return None, "A valid account is required."
        note = str(data.get("note", "")).strip()[:300]
        return {
            "type": tx_type,
            "amount": amount,
            "date": tx_date,
            "category": category[:80],
            "account_id": account_id,
            "note": note,
        }, None

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/accounts")
    def list_accounts():
        with db() as conn:
            rows = conn.execute(
                """
                SELECT a.*,
                    ROUND(a.opening_balance + COALESCE(SUM(
                        CASE WHEN t.type IN ('income','transfer_in') THEN t.amount
                             ELSE -t.amount END
                    ), 0), 2) AS balance
                FROM accounts a
                LEFT JOIN transactions t ON t.account_id = a.id
                GROUP BY a.id
                ORDER BY a.created_at, a.id
                """
            ).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.post("/api/accounts")
    def create_account():
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "")).strip()
        account_type = str(data.get("type", "")).strip()
        try:
            opening = round(float(data.get("opening_balance", 0)), 2)
        except (TypeError, ValueError):
            return error("Opening balance must be a number.")
        if not name:
            return error("Account name is required.")
        if account_type not in {"cash", "bank", "card"}:
            return error("Account type must be cash, bank, or card.")
        try:
            with db() as conn:
                cursor = conn.execute(
                    "INSERT INTO accounts(name, type, opening_balance) VALUES (?, ?, ?)",
                    (name[:80], account_type, opening),
                )
                account_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            return error("An account with that name already exists.")
        return jsonify({"id": account_id, "message": "Account created."}), 201

    @app.delete("/api/accounts/<int:account_id>")
    def delete_account(account_id):
        with db() as conn:
            used = conn.execute("SELECT 1 FROM transactions WHERE account_id = ?", (account_id,)).fetchone()
            if used:
                return error("This account has transactions and cannot be deleted.", 409)
            cursor = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
            if not cursor.rowcount:
                return error("Account not found.", 404)
        return jsonify({"message": "Account deleted."})

    @app.get("/api/transactions")
    def list_transactions():
        month = request.args.get("month", "")
        params = []
        where = ""
        if month:
            if not valid_month(month):
                return error("Month must use YYYY-MM format.")
            where = "WHERE substr(t.transaction_date, 1, 7) = ?"
            params.append(month)
        with db() as conn:
            rows = conn.execute(
                f"""
                SELECT t.*, a.name AS account_name
                FROM transactions t JOIN accounts a ON a.id = t.account_id
                {where}
                ORDER BY t.transaction_date DESC, t.id DESC
                """,
                params,
            ).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.post("/api/transactions")
    def create_transaction():
        payload, message = transaction_payload(request.get_json(silent=True) or {})
        if message:
            return error(message)
        with db() as conn:
            if not account_exists(conn, payload["account_id"]):
                return error("Account not found.", 404)
            cursor = conn.execute(
                """INSERT INTO transactions(type, amount, transaction_date, category, account_id, note)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (payload["type"], payload["amount"], payload["date"], payload["category"], payload["account_id"], payload["note"]),
            )
            tx_id = cursor.lastrowid
        return jsonify({"id": tx_id, "message": "Transaction added."}), 201

    @app.put("/api/transactions/<int:tx_id>")
    def update_transaction(tx_id):
        payload, message = transaction_payload(request.get_json(silent=True) or {})
        if message:
            return error(message)
        with db() as conn:
            existing = conn.execute("SELECT transfer_group FROM transactions WHERE id = ?", (tx_id,)).fetchone()
            if not existing:
                return error("Transaction not found.", 404)
            if existing["transfer_group"]:
                return error("Transfers must be deleted and recreated instead of edited.", 409)
            if not account_exists(conn, payload["account_id"]):
                return error("Account not found.", 404)
            conn.execute(
                """UPDATE transactions SET type=?, amount=?, transaction_date=?, category=?, account_id=?, note=?
                   WHERE id=?""",
                (payload["type"], payload["amount"], payload["date"], payload["category"], payload["account_id"], payload["note"], tx_id),
            )
        return jsonify({"message": "Transaction updated."})

    @app.delete("/api/transactions/<int:tx_id>")
    def delete_transaction(tx_id):
        with db() as conn:
            row = conn.execute("SELECT transfer_group FROM transactions WHERE id = ?", (tx_id,)).fetchone()
            if not row:
                return error("Transaction not found.", 404)
            if row["transfer_group"]:
                conn.execute("DELETE FROM transactions WHERE transfer_group = ?", (row["transfer_group"],))
            else:
                conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
        return jsonify({"message": "Transaction deleted."})

    @app.post("/api/transfers")
    def create_transfer():
        data = request.get_json(silent=True) or {}
        try:
            source = int(data.get("from_account_id"))
            destination = int(data.get("to_account_id"))
            amount = round(float(data.get("amount", 0)), 2)
        except (TypeError, ValueError):
            return error("Transfer accounts and amount are required.")
        tx_date = str(data.get("date", "")).strip()
        note = str(data.get("note", "")).strip()[:300]
        if source == destination:
            return error("Source and destination accounts must be different.")
        if amount <= 0:
            return error("Amount must be greater than zero.")
        if not valid_date(tx_date):
            return error("Date must use YYYY-MM-DD format.")
        with db() as conn:
            if not account_exists(conn, source) or not account_exists(conn, destination):
                return error("One of the selected accounts does not exist.", 404)
            group = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO transactions(type, amount, transaction_date, category, account_id, note, transfer_group)
                   VALUES ('transfer_out', ?, ?, 'Transfer', ?, ?, ?)""",
                (amount, tx_date, source, note, group),
            )
            conn.execute(
                """INSERT INTO transactions(type, amount, transaction_date, category, account_id, note, transfer_group)
                   VALUES ('transfer_in', ?, ?, 'Transfer', ?, ?, ?)""",
                (amount, tx_date, destination, note, group),
            )
        return jsonify({"message": "Transfer completed."}), 201

    @app.get("/api/budgets")
    def list_budgets():
        month = request.args.get("month", date.today().strftime("%Y-%m"))
        if not valid_month(month):
            return error("Month must use YYYY-MM format.")
        with db() as conn:
            rows = conn.execute(
                """
                SELECT b.id, b.month, b.category, b.amount,
                       ROUND(COALESCE(SUM(t.amount), 0), 2) AS spent
                FROM budgets b
                LEFT JOIN transactions t ON t.category = b.category
                    AND t.type = 'expense'
                    AND substr(t.transaction_date, 1, 7) = b.month
                WHERE b.month = ?
                GROUP BY b.id ORDER BY b.category
                """,
                (month,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["percentage"] = round(item["spent"] / item["amount"] * 100, 1) if item["amount"] else 0
            item["status"] = "danger" if item["percentage"] >= 100 else "warning" if item["percentage"] >= 80 else "safe"
            result.append(item)
        return jsonify(result)

    @app.post("/api/budgets")
    def upsert_budget():
        data = request.get_json(silent=True) or {}
        month = str(data.get("month", "")).strip()
        category = str(data.get("category", "")).strip()
        try:
            amount = round(float(data.get("amount", 0)), 2)
        except (TypeError, ValueError):
            return error("Budget amount must be a number.")
        if not valid_month(month):
            return error("Month must use YYYY-MM format.")
        if not category:
            return error("Category is required.")
        if amount <= 0:
            return error("Budget amount must be greater than zero.")
        with db() as conn:
            conn.execute(
                """INSERT INTO budgets(month, category, amount) VALUES (?, ?, ?)
                   ON CONFLICT(month, category) DO UPDATE SET amount=excluded.amount""",
                (month, category[:80], amount),
            )
        return jsonify({"message": "Budget saved."}), 201

    @app.delete("/api/budgets/<int:budget_id>")
    def delete_budget(budget_id):
        with db() as conn:
            cursor = conn.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
            if not cursor.rowcount:
                return error("Budget not found.", 404)
        return jsonify({"message": "Budget deleted."})

    @app.get("/api/dashboard")
    def dashboard():
        month = request.args.get("month", date.today().strftime("%Y-%m"))
        if not valid_month(month):
            return error("Month must use YYYY-MM format.")
        with db() as conn:
            totals = conn.execute(
                """SELECT
                    ROUND(COALESCE(SUM(CASE WHEN type='income' THEN amount END),0),2) AS income,
                    ROUND(COALESCE(SUM(CASE WHEN type='expense' THEN amount END),0),2) AS expense
                   FROM transactions WHERE substr(transaction_date,1,7)=?""",
                (month,),
            ).fetchone()
            categories = conn.execute(
                """SELECT category, ROUND(SUM(amount),2) AS amount FROM transactions
                   WHERE type='expense' AND substr(transaction_date,1,7)=?
                   GROUP BY category ORDER BY amount DESC""",
                (month,),
            ).fetchall()
            trend = conn.execute(
                """
                WITH RECURSIVE months(m, n) AS (
                    SELECT date(? || '-01'), 1
                    UNION ALL SELECT date(m, '-1 month'), n + 1 FROM months WHERE n < 6
                )
                SELECT substr(months.m,1,7) AS month,
                    ROUND(COALESCE(SUM(CASE WHEN t.type='income' THEN t.amount END),0),2) AS income,
                    ROUND(COALESCE(SUM(CASE WHEN t.type='expense' THEN t.amount END),0),2) AS expense
                FROM months LEFT JOIN transactions t ON substr(t.transaction_date,1,7)=substr(months.m,1,7)
                GROUP BY months.m ORDER BY months.m
                """,
                (month,),
            ).fetchall()
        return jsonify({
            "month": month,
            "income": totals["income"],
            "expense": totals["expense"],
            "net": round(totals["income"] - totals["expense"], 2),
            "categories": [dict(row) for row in categories],
            "trend": [dict(row) for row in trend],
        })

    def decode_csv(upload):
        if not upload or not upload.filename.lower().endswith(".csv"):
            raise ValueError("Please select a CSV file.")
        raw = upload.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV must use UTF-8 encoding.") from exc
        return list(csv.DictReader(io.StringIO(text)))

    @app.post("/api/import/preview")
    def import_preview():
        try:
            rows = decode_csv(request.files.get("file"))
        except ValueError as exc:
            return error(str(exc))
        if not rows:
            return error("The CSV has no data rows.")
        return jsonify({"columns": list(rows[0].keys()), "rows": rows[:5], "total_rows": len(rows)})

    @app.post("/api/import")
    def import_transactions():
        try:
            rows = decode_csv(request.files.get("file"))
        except ValueError as exc:
            return error(str(exc))
        mapping = {key: request.form.get(key, "") for key in ("date", "amount", "type", "category", "account", "note")}
        required = ("date", "amount", "type", "category", "account")
        if any(not mapping[key] for key in required):
            return error("Map all required columns before importing.")
        imported = skipped = 0
        problems = []
        with db() as conn:
            accounts = {row["name"].strip().lower(): row["id"] for row in conn.execute("SELECT id,name FROM accounts")}
            for number, row in enumerate(rows, start=2):
                try:
                    tx_type = row.get(mapping["type"], "").strip().lower()
                    if tx_type not in {"income", "expense"}:
                        raise ValueError("type must be income or expense")
                    amount = round(float(row.get(mapping["amount"], "")), 2)
                    if amount <= 0:
                        raise ValueError("amount must be greater than zero")
                    tx_date = row.get(mapping["date"], "").strip()
                    if not valid_date(tx_date):
                        raise ValueError("date must use YYYY-MM-DD")
                    category = row.get(mapping["category"], "").strip()
                    account_name = row.get(mapping["account"], "").strip()
                    if not category:
                        raise ValueError("category is missing")
                    account_id = accounts.get(account_name.lower())
                    if not account_id:
                        raise ValueError(f"account '{account_name}' does not exist")
                    note = row.get(mapping["note"], "").strip() if mapping["note"] else ""
                    fingerprint = "|".join([tx_date, f"{amount:.2f}", tx_type, category.lower(), account_name.lower(), note.lower()])
                    digest = hashlib.sha256(fingerprint.encode()).hexdigest()
                    try:
                        conn.execute(
                            """INSERT INTO transactions(type,amount,transaction_date,category,account_id,note,import_hash)
                               VALUES (?,?,?,?,?,?,?)""",
                            (tx_type, amount, tx_date, category[:80], account_id, note[:300], digest),
                        )
                        imported += 1
                    except sqlite3.IntegrityError:
                        skipped += 1
                except (ValueError, TypeError) as exc:
                    problems.append({"row": number, "error": str(exc)})
        return jsonify({"imported": imported, "duplicates_skipped": skipped, "errors": problems})

    @app.cli.command("init-db")
    def init_db_command():
        init_db()
        print("Database initialized.")

    @app.cli.command("seed")
    def seed_command():
        init_db()
        today_month = date.today().strftime("%Y-%m")
        with db() as conn:
            if conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]:
                print("Seed data already exists.")
                return
            conn.executemany(
                "INSERT INTO accounts(name,type,opening_balance) VALUES (?,?,?)",
                [("Wallet", "cash", 1500), ("Main Bank", "bank", 25000), ("Credit Card", "card", 0)],
            )
            ids = {row["name"]: row["id"] for row in conn.execute("SELECT id,name FROM accounts")}
            conn.executemany(
                """INSERT INTO transactions(type,amount,transaction_date,category,account_id,note)
                   VALUES (?,?,?,?,?,?)""",
                [
                    ("income", 45000, f"{today_month}-01", "Salary", ids["Main Bank"], "Monthly salary"),
                    ("expense", 9000, f"{today_month}-03", "Rent", ids["Main Bank"], "Room rent"),
                    ("expense", 2500, f"{today_month}-07", "Food", ids["Credit Card"], "Groceries"),
                    ("expense", 800, f"{today_month}-10", "Transport", ids["Wallet"], "Local travel"),
                ],
            )
            conn.executemany(
                "INSERT INTO budgets(month,category,amount) VALUES (?,?,?)",
                [(today_month, "Food", 5000), (today_month, "Transport", 2500), (today_month, "Rent", 10000)],
            )
        print("Demo data inserted.")

    init_db()
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
