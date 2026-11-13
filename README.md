# Swiftella Loans – application database

A Django app that takes a UK loan application, saves it to a database and gives the customer a PDF invoice of their loan.

## What it does

1. **Application form** at `/`: loan amount (£100–£1,000), term (1, 3 or 6 months), purpose, personal details, UK address, income and outgoings, UK bank account, and consents. It shows a live quote as the customer types.
2. **UK validation**: Royal Mail postcode format, HMRC National Insurance number rules, 6-digit sort code, 8-digit account number, UK phone numbers, and a minimum age of 18.
3. **Database**: saves `Customer`, `LoanApplication`, `ScheduledRepayment` and an append-only `AuditEvent` log. Money is stored in whole pence. NI numbers and bank account numbers are **encrypted at rest** (Fernet). Only the last digits are kept in plain text, for searching.
4. **Pricing**: fixed at the moment the customer submits. It applies the FCA high-cost short-term credit cap: at most 0.8% of the amount borrowed per day, and total charges never more than the amount borrowed. The £15 fee counts inside the cap. This matches the calculator on the live site.
5. **PDF invoice** (ReportLab): invoice number, application reference, loan summary, repayment schedule, the masked bank account and risk warnings. Only the browser that submitted the application, or a staff user, can open it.
6. **Staff admin** at `/staff/`: search and filter applications, change their status (each change is audited), open any invoice, and export to CSV. The export leaves out NI numbers and full account numbers and guards against spreadsheet formula injection.

## Run locally

```bash
pip install -r requirements.txt
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/ for the form and http://127.0.0.1:8000/staff/ for the admin.

## Tests

```bash
DJANGO_DEBUG=1 python manage.py test loans
```

## Deploy on Railway

1. Add a PostgreSQL service. Railway sets `DATABASE_URL` for you.
2. Set the variables listed in `.env.example`. Generate the two keys like this:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(50))"                               # DJANGO_SECRET_KEY
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # FIELD_ENCRYPTION_KEY
   ```
   **Back up `FIELD_ENCRYPTION_KEY`.** If it is lost, the encrypted NI and account numbers cannot be recovered.
3. The `Procfile` runs migrations on release and starts gunicorn.
4. Create an admin with `railway run python manage.py createsuperuser`.

## Before taking real customers

- The quote charges 0.8% per day on the **full** amount for the whole term, which is the most the cap allows. On multi-month loans, charging only on the balance still owed would cost the customer less. Agree the real pricing before going live.
- Bank details are checked for format only. Use a modulus-check / Confirmation of Payee service to verify them before paying out.
- There are no credit, fraud or affordability decisions yet. Staff set the status by hand.
- No confirmation emails are sent yet.
- Add rate limiting (for example django-ratelimit, or at the proxy) to the form.
