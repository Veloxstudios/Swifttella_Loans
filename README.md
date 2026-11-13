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

Staff must use **two-factor sign-in**. The first time you sign in to `/staff/`, scan the QR code with an authenticator app (Google Authenticator, Microsoft Authenticator, 1Password…) and save the backup codes. If someone loses their phone, a superuser can use **Reset two-factor sign-in** on the Users page, or run:

```bash
python manage.py reset_staff_2fa <username>
```

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
3. The `Procfile` runs migrations and creates the rate-limit cache table on release, then starts gunicorn.
4. Create an admin with `railway run python manage.py createsuperuser`.
5. Add a daily Railway cron job that removes personal data from old applications that never became a loan:
   ```bash
   python manage.py anonymise_old_applications --apply
   ```
   Run it without `--apply` to see what it would do.
6. Set up email from your own domain so customers get their confirmation and invoice. Follow **[EMAIL_SETUP.md](EMAIL_SETUP.md)**: it covers the domain, the email provider, the DNS records (SPF, DKIM, DMARC) and the three settings `EMAIL_DOMAIN`, `EMAIL_PROVIDER` and `EMAIL_API_KEY`. Check it with `python manage.py send_test_email you@example.com`.

Locally, each email is saved as a `.log` file in `sent_emails/` instead of being sent. It holds the full message, including the HTML and the attached invoice.

## Before taking real customers

See **[COMPLIANCE.md](COMPLIANCE.md)** for the full FCA, data protection and security checklist: what the app already does, which settings to fill in, and what still needs building or signing off. The most important open items:

- FCA authorisation, and the status statement (`LENDER_FCA_NUMBER`) and price comparison link (`PRICE_COMPARISON_URL`) that come with it.
- Credit reference agency checks and income verification. Today's affordability check only uses what the customer tells us.
- Pre-contract information (SECCI), the credit agreement and the 14-day withdrawal right.
- Bank details are only format-checked. Use a modulus check / Confirmation of Payee before paying out.
