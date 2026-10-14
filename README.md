# CloudStock — Inventory & Billing System

## Run on Windows / VS Code
1. Extract this ZIP and open the `CloudStock` folder in VS Code.
2. Open Terminal → New Terminal.
3. Run:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe app.py
   ```
4. Open http://127.0.0.1:5000

The app creates a local SQLite database and sample products automatically. No images or internet image URLs are required for the interface.

## Included
- Professional responsive dashboard with 7-day sales chart
- Product add/edit/delete, search and category filtering
- Low-stock indicators
- Billing cart, quantity validation, tax percentage, invoice and print-to-PDF
- Sales history; stock decreases after successful sale
- SQLite locally, configurable for MySQL / AWS RDS later
- `/health` endpoint for deployment checks

## Configure MySQL later
Copy `.env.example` to `.env` and set:
`DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/inventory_db`
Use a strong SECRET_KEY. Never commit `.env` or expose database credentials. On AWS, keep RDS private and allow EC2 access only through its security group; use an EC2 IAM role for S3 permissions.

Student project starter only. Before real business use, add authentication, CSRF protection, audit logs, backups, and verified GST/invoice compliance. Tax defaults to 0% and must be configured appropriately.
