# Submission Response

I built a responsive full-stack Personal Budget Tracker using Python, Flask, SQLite, HTML, CSS, JavaScript, and Chart.js. The application supports cash, bank, and card accounts; income and expense transactions; linked account transfers; monthly category budgets with 80% and 100% warnings; CSV preview and column mapping; row-level import error reporting; duplicate prevention; and dashboard charts. Account balances are derived from transaction history so they remain correct after edits, deletions, and transfers. I also added server-side validation, demo seed data, a sample CSV, eight automated backend tests, setup documentation, and a `.env.example` file.

## Video walkthrough outline

1. Introduce the application and technology stack.
2. Show the dashboard totals and charts.
3. Add an account and an expense transaction.
4. Edit or delete a transaction and show the updated balance.
5. Transfer money between two accounts and explain why it is excluded from income and expenses.
6. Set a budget and demonstrate the warning progress bar.
7. Preview and import `sample_transactions.csv`, then import it again to demonstrate duplicate prevention.
8. Briefly show the Flask API, SQLite data model, tests, README, and `.env.example`.
9. Explain that the hardest part was keeping balances accurate while representing transfers as two linked movements.

