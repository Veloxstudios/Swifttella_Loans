# Security and regulatory checklist

Swiftella Loans offers **high-cost short-term credit (HCSTC)** to UK consumers. That brings in the
FCA Consumer Credit sourcebook (CONC), the Consumer Credit Act 1974, the Consumer Duty, UK GDPR and the
Data Protection Act 2018.

This file lists what the app does today and what still needs a person to do or decide. **It is not legal
advice.** Before taking real customers, have it reviewed by a compliance professional who knows FCA consumer
credit rules.

Status key: ✅ done in the app · ⚙️ needs a setting or task before launch · ⚠️ not built yet, needed before lending

---

## 1. FCA authorisation and status

| Requirement | Status |
|---|---|
| Firm must be FCA-authorised for consumer credit lending before it lends | ⚠️ Business task. The app is not a substitute. |
| Status statement on the website ("authorised and regulated by the FCA", firm reference number) | ⚙️ Shown in the footer once `LENDER_FCA_NUMBER` is set. Nothing is claimed until then. |
| Company name, number and registered office | ⚙️ Set `LENDER_NAME`, `LENDER_COMPANY_NUMBER`, `LENDER_ADDRESS`. |

## 2. Financial promotions (CONC 3)

| Requirement | Status |
|---|---|
| HCSTC risk warning, exact wording, prominent (CONC 3.4.1R) | ✅ Banner at the top of the form and in the footer. |
| Link to an FCA-authorised price comparison website (HCSTC rule) | ⚙️ Set `PRICE_COMPARISON_URL` and `PRICE_COMPARISON_NAME`. The footer shows it once set. |
| Representative APR and representative example when costs are shown (CONC 3.5) | ⚠️ The quote shows a 30-day maximum-cost APR, matching the live calculator. The live site says a representative example is still awaiting approval. Compliance must confirm the wording before launch. |
| Promotions must be clear, fair and not misleading (CONC 3.3) | ⚠️ Needs sign-off on all page wording. |

## 3. Price cap (CONC 5A)

| Requirement | Status |
|---|---|
| Interest and fees at most 0.8% a day of the amount borrowed | ✅ `loans/pricing.py`, with tests. |
| Total cost never more than 100% of the amount borrowed | ✅ Enforced in pricing, with tests. |
| Default fees capped at £15 | ⚠️ No default or late fees exist yet. Any future fee must stay within the cap. |

## 4. Creditworthiness and affordability (CONC 5.2A)

| Requirement | Status |
|---|---|
| Assess affordability before lending | ✅ Minimum check: income minus essentials minus the repayment must leave at least `AFFORDABILITY_BUFFER_PENCE` (default £100). The admin **refuses approval** when it fails. |
| Verify income and use credit reference agency (CRA) data, not just what the customer says | ⚠️ Not built. Staff must check manually until a CRA integration exists. The admin reminds them. |
| Written creditworthiness policy, with records of each decision | ⚠️ Policy is a business task. Status changes are already recorded in the audit trail. |

## 5. Before and after the agreement (CCA, CONC 4 and 6)

| Requirement | Status |
|---|---|
| Pre-contract credit information (SECCI) and adequate explanations (CONC 4.2) | ⚠️ Not built. Needed before any agreement is signed. The invoice says it is not a credit agreement. |
| Regulated credit agreement with the required terms | ⚠️ Not built. |
| 14-day right of withdrawal (CCA s66A) | ⚠️ Must appear in the agreement and be honoured. |
| At most 2 refinances or rollovers (CONC 6.7.23R) | ⚠️ Rollovers don't exist yet. Enforce this if they are added. |
| Continuous payment authority: at most 2 failed attempts, no part-payments without consent (CONC 7.6) | ⚠️ Collection is not built. The invoice mentions CPA, so wording and process need review. |
| Fair treatment of customers in financial difficulty (CONC 7) | ⚠️ Process and staff training. |
| Complaints handling, and Financial Ombudsman Service details (DISP) | ⚠️ The live site has a Complaints page. Its content needs review. |

## 6. Consumer Duty (PRIN 2A)

| Requirement | Status |
|---|---|
| Fair value assessment for the product | ⚠️ The live site says pricing still needs fair-value approval. |
| Clear communications that customers understand | ✅ Plain-English form and quote. ⚠️ Needs testing with real customers. |
| Monitoring customer outcomes | ⚠️ Not built. |

## 7. Data protection (UK GDPR and DPA 2018)

| Requirement | Status |
|---|---|
| Register with the ICO and pay the fee | ⚙️ Business task. Set `LENDER_ICO_NUMBER` to show it in the footer. |
| Privacy information at the point of collection (Art. 13) | ✅ Summary above the Submit button, linking to the full privacy notice on the main site. ⚠️ The full notice must name the CRAs and fraud prevention agencies used. |
| Lawful basis for each use, and consent for credit searches | ✅ Separate unticked boxes for the credit check and for marketing. ⚠️ Confirm the lawful bases with your DPO. |
| Encryption of the most sensitive data | ✅ NI and bank account numbers are encrypted at rest (Fernet). The admin and CSV export only ever show the last digits. |
| Storage limitation | ✅ `python manage.py anonymise_old_applications --apply` removes personal data from applications that didn't become a loan after `DATA_RETENTION_DAYS` (default 365). ⚙️ Schedule it daily (see README). ⚠️ Approved loans need their own retention rule, typically 6 years after the account closes. |
| Confirmation emails share only what's needed | ✅ The email shows the loan figures and the last 4 digits of the bank account, never the NI or full account number. It attaches the invoice, says no decision has been made and includes the risk warning and an anti-fraud notice. Each send or failure is recorded in the audit trail. |
| Accountability: who accessed what | ✅ The audit trail records submissions, staff views, status changes, CSV exports, invoice downloads and data removal. Nobody can delete applications or customers through the admin. |
| Data subject requests (access, correction, deletion) | ⚠️ No self-service yet. Handle manually through the admin, and record what you did. |
| Data Protection Impact Assessment (DPIA) | ⚠️ Required for credit scoring and large-scale financial data. Business task. |
| Email provider is a data processor | ⚙️ Sign the provider's DPA, name it in the privacy notice, and check UK transfer terms for a US provider. See EMAIL_SETUP.md. |
| Breach process: report to the ICO within 72 hours | ⚠️ Business task. |

## 8. Application security

| Control | Status |
|---|---|
| HTTPS only, HSTS (1 year, subdomains, preload) | ✅ When `DJANGO_DEBUG` is off. |
| Secure, HttpOnly, SameSite cookies | ✅ |
| Sessions end after 30 minutes idle and when the browser closes | ✅ `SESSION_IDLE_SECONDS`. |
| CSRF protection | ✅ Django's, on every form. |
| Content-Security-Policy (own files only, no inline scripts, no framing) | ✅ `loans/security.py`. |
| Permissions-Policy, X-Frame-Options, nosniff, Referrer-Policy, COOP | ✅ |
| Pages with personal data not cached | ✅ `Cache-Control: no-store` on applications, invoices, staff pages and form posts. |
| Rate limit on applications | ✅ 5 per IP address per hour (`APPLY_RATE_LIMIT`). |
| Staff sign-in lockout | ✅ 5 failures locks that username and IP address out for 15 minutes. |
| IP address can't be faked through `X-Forwarded-For` | ✅ Only the address added by Railway's proxy is trusted (`TRUSTED_PROXIES`). |
| Strong staff passwords (12+ characters, not common) | ✅ |
| Two-factor sign-in for staff | ✅ Every staff sign-in needs a code from an authenticator app (TOTP) after the password. New staff are sent to a setup page with a QR code and 10 single-use backup codes. Wrong codes lock out after 5 tries. Staff invoice access also needs 2FA. A lost phone is reset with the Users page action or `manage.py reset_staff_2fa <username>`. |
| Limit staff permissions (not everyone a superuser) | ⚙️ Create a "Loan reviewers" group with only the permissions it needs. |
| Encryption key backed up and kept separately from the database | ⚙️ `FIELD_ENCRYPTION_KEY`. Losing it makes NI and account numbers unrecoverable. |
| Database backups, encrypted, restore tested | ⚙️ Railway Postgres backups. |
| Dependency updates and security scanning | ⚙️ Turn on GitHub Dependabot alerts. |
| Bank details verified (modulus check / Confirmation of Payee) before paying out | ⚠️ Not built. Only the format is checked. |
| Customer email sent from your own domain with SPF, DKIM and DMARC | ⚙️ Follow EMAIL_SETUP.md. `check --deploy` warns until it's set up. Move DMARC to `p=quarantine` once reports are clean, to stop people faking your emails. |
| Independent penetration test | ⚠️ Recommended before launch. |

---

## Settings added for this checklist

| Variable | Default | Purpose |
|---|---|---|
| `LENDER_FCA_NUMBER` | (blank) | Shows the FCA status statement. |
| `LENDER_COMPANY_NUMBER`, `LENDER_ICO_NUMBER` | (blank) | Footer legal details. |
| `PRICE_COMPARISON_URL`, `PRICE_COMPARISON_NAME` | (blank) | Required HCSTC price comparison link. |
| `DATA_RETENTION_DAYS` | `365` | When unfunded applications are anonymised. |
| `AFFORDABILITY_BUFFER_PENCE` | `10000` (£100) | Money that must be left after the repayment. |
| `APPLY_RATE_LIMIT`, `APPLY_RATE_WINDOW` | `5`, `3600` | Applications per IP address per window. |
| `LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_SECONDS` | `5`, `900` | Staff sign-in lockout. |
| `SESSION_IDLE_SECONDS` | `1800` | Session timeout. |
| `TRUSTED_PROXIES` | `1` in production | Proxies in front of the app (Railway adds one). |
