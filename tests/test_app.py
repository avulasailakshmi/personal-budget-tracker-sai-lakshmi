import io

import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db")})
    with app.test_client() as client:
        yield client


def add_account(client, name="Main Bank", account_type="bank", balance=1000):
    response = client.post("/api/accounts", json={"name": name, "type": account_type, "opening_balance": balance})
    assert response.status_code == 201
    return response.get_json()["id"]


def test_account_creation_and_balance(client):
    add_account(client)
    account = client.get("/api/accounts").get_json()[0]
    assert account["name"] == "Main Bank"
    assert account["balance"] == 1000


def test_rejects_invalid_transaction(client):
    account_id = add_account(client)
    response = client.post("/api/transactions", json={"type": "expense", "amount": -20, "date": "2026-10-10", "category": "Food", "account_id": account_id})
    assert response.status_code == 400
    assert "greater than zero" in response.get_json()["error"]


def test_transaction_updates_balance(client):
    account_id = add_account(client)
    client.post("/api/transactions", json={"type": "income", "amount": 500, "date": "2026-10-10", "category": "Salary", "account_id": account_id})
    client.post("/api/transactions", json={"type": "expense", "amount": 120, "date": "2026-10-11", "category": "Food", "account_id": account_id})
    assert client.get("/api/accounts").get_json()[0]["balance"] == 1380


def test_transfer_preserves_total_balance(client):
    source = add_account(client, "Bank", "bank", 1000)
    destination = add_account(client, "Wallet", "cash", 100)
    response = client.post("/api/transfers", json={"from_account_id": source, "to_account_id": destination, "amount": 250, "date": "2026-10-12"})
    assert response.status_code == 201
    accounts = {a["name"]: a["balance"] for a in client.get("/api/accounts").get_json()}
    assert accounts == {"Bank": 750, "Wallet": 350}
    assert sum(accounts.values()) == 1100


def test_deleting_transfer_removes_both_sides(client):
    source = add_account(client, "Bank", "bank", 1000)
    destination = add_account(client, "Wallet", "cash", 100)
    client.post("/api/transfers", json={"from_account_id": source, "to_account_id": destination, "amount": 250, "date": "2026-10-12"})
    transactions = client.get("/api/transactions?month=2026-10").get_json()
    assert len(transactions) == 2
    client.delete(f"/api/transactions/{transactions[0]['id']}")
    assert client.get("/api/transactions?month=2026-10").get_json() == []


def test_budget_warning_thresholds(client):
    account_id = add_account(client)
    client.post("/api/budgets", json={"month": "2026-10", "category": "Food", "amount": 100})
    client.post("/api/transactions", json={"type": "expense", "amount": 85, "date": "2026-10-10", "category": "Food", "account_id": account_id})
    budget = client.get("/api/budgets?month=2026-10").get_json()[0]
    assert budget["percentage"] == 85
    assert budget["status"] == "warning"


def test_csv_import_reports_bad_rows_and_skips_duplicates(client):
    add_account(client, "Main Bank")
    csv_text = "date,amount,type,category,account,note\n2026-10-01,100,income,Salary,Main Bank,Pay\nbad-date,20,expense,Food,Main Bank,Bad\n"
    mapping = {"date": "date", "amount": "amount", "type": "type", "category": "category", "account": "account", "note": "note"}
    response = client.post("/api/import", data={**mapping, "file": (io.BytesIO(csv_text.encode()), "data.csv")}, content_type="multipart/form-data")
    result = response.get_json()
    assert result["imported"] == 1
    assert len(result["errors"]) == 1
    response = client.post("/api/import", data={**mapping, "file": (io.BytesIO(csv_text.encode()), "data.csv")}, content_type="multipart/form-data")
    assert response.get_json()["duplicates_skipped"] == 1


def test_dashboard_excludes_transfers_from_income_and_expense(client):
    source = add_account(client, "Bank", "bank", 1000)
    destination = add_account(client, "Wallet", "cash", 100)
    client.post("/api/transfers", json={"from_account_id": source, "to_account_id": destination, "amount": 200, "date": "2026-10-12"})
    dashboard = client.get("/api/dashboard?month=2026-10").get_json()
    assert dashboard["income"] == 0
    assert dashboard["expense"] == 0

