# Personal Budget Tracker

A responsive full-stack personal finance application for managing accounts, income, expenses, transfers, monthly category budgets, CSV imports, and visual reports.

## Features

- Cash, bank, and card accounts with continuously calculated balances
- Income and expense transactions with date, category, account, and notes
- Safe account-to-account transfers that do not affect income or expense totals
- Edit and delete support while preserving accurate balances
- Monthly category budgets with progress bars and warnings at 80% and 100%
- CSV preview, column mapping, row-level validation, and duplicate prevention
- Dashboard charts for category spending and six-month income versus expenses
- Responsive layout for phones and laptops
- Server-side validation with clear API and UI error messages
- Demo seed data and automated backend tests

## Technology

- Frontend: HTML, CSS, JavaScript, Chart.js
- Backend: Python and Flask
- Database: SQLite
- Tests: Pytest

## Data model

### accounts

Stores an account name, type, and opening balance. Current balance is calculated from the opening balance plus all related transaction movements.

### transactions

Stores income, expense, transfer-in, and transfer-out movements. Transfers share a unique `transfer_group`, allowing both sides to be removed together. Imported rows receive a SHA-256 fingerprint in `import_hash` to prevent duplicates.

### budgets

Stores a unique category budget for each month. Spending is calculated from expense transactions only.

## Main design decisions

1. Balances are calculated from transaction history instead of being manually updated, preventing balance drift after edits or deletions.
2. Transfers are stored as two linked movements and excluded from income and expense reporting.
3. CSV import processes each row independently. Invalid rows are reported while valid rows continue importing.
4. Imported transaction fingerprints prevent the same rows from being inserted twice.
5. Validation is performed by the backend even though the browser also performs basic validation.

## Setup

1. Install Python 3.10 or newer.
2. Create and activate a virtual environment.

   Windows PowerShell:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   macOS or Linux:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` if environment customization is needed. Never commit `.env`.
5. Add demonstration data:

   ```bash
   flask --app app seed
   ```

6. Run the application:

   ```bash
   flask --app app run --debug
   ```

7. Open `http://127.0.0.1:5000`.

## Demo data

Run `flask --app app seed`. The application does not require authentication, so no demo login is needed. It creates Wallet, Main Bank, and Credit Card accounts, transactions, and monthly budgets.

## CSV format

Use `sample_transactions.csv` as an example. Required logical fields are date, amount, type, category, and account. The column names can differ because the import screen supports column mapping.

- Dates must use `YYYY-MM-DD`.
- Type must be `income` or `expense`.
- Account names must already exist in the application.
- Bad rows are listed and skipped.
- Re-imported rows are detected and skipped.

## Tests

Run:

```bash
pytest -q
```

The test suite covers account balances, invalid inputs, income and expense calculations, transfers, transfer deletion, budget warnings, CSV error handling, duplicate prevention, and dashboard reporting.

## Completed scope

All required core features are implemented. Optional repeating transactions and CSV export are not included. With more time, these would be added along with user authentication and cloud deployment.

## AI tools used

ChatGPT was used to help plan the application structure, generate implementation suggestions, review validation logic, and prepare test cases. Every part of the final code was reviewed and tested for this assignment.

