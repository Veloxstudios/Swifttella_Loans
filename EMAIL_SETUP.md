# Sending email from your own domain

Customers get an email with their invoice when they apply. For it to arrive in the inbox (not spam) and
come from your business, it must be sent from **your own domain** through an **email provider**, with the
domain's DNS records proving the provider is allowed to send for you.

The app already does the sending. You need to do four things once:

1. Own a domain
2. Pick an email provider and add your domain
3. Add the provider's DNS records
4. Give the app three settings

---

## 1. Own a domain

For example `swiftella.co.uk`, bought from a registrar such as Cloudflare, Namecheap, GoDaddy or 123-reg.
The `up.railway.app` address can't be used: you don't control its DNS.

Optional but tidy: also point the website at it (`apply.swiftella.co.uk`) under Railway → Settings →
Networking → Custom domain.

## 2. Pick an email provider

All of these work with the app. They send over HTTPS, so Railway's SMTP restrictions don't matter.

| Provider | `EMAIL_PROVIDER` | Notes |
|---|---|---|
| **Postmark** (recommended) | `postmark` | Built for transactional email like confirmations. Very good inbox delivery. Use a **Server API token**. |
| Mailgun | `mailgun` | EU region is used by default, so UK/EU customer data stays in the EU. |
| Brevo | `brevo` | EU-based, free plan of about 300 emails a day. |
| Resend | `resend` | Simple setup. |
| SendGrid | `sendgrid` | |
| Any SMTP server | `smtp` | Also set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`. |

In the provider's dashboard, add your domain as a **sending domain** (Postmark calls it a "Sender Signature" /
"Domain"). The provider then shows you the DNS records for step 3.

**Data protection:** the provider processes customers' names, emails and loan details. Sign its data processing
agreement (DPA), and name it in your privacy notice as a processor. For a US provider (Postmark, Resend,
SendGrid), check its UK transfer terms (UK IDTA or the UK Extension to the EU-US Data Privacy Framework).

## 3. Add the DNS records

Add these at whoever manages your domain's DNS. Copy the exact values from your provider's dashboard;
the ones below only show the shape.

| Record | Type | Name | Value (example) | What it does |
|---|---|---|---|---|
| **DKIM** | TXT (or CNAME) | e.g. `pm._domainkey` | a long key from the provider | Signs every email so inboxes know it's really from you. |
| **Return-Path / bounce** | CNAME | e.g. `pm-bounces` | e.g. `pm.mtasv.net` | Handles bounces and makes SPF pass for your domain. |
| **SPF** | TXT | `@` | `v=spf1 include:<provider> ~all` | Lists who may send for the domain. Only needed if your provider asks; keep **one** SPF record and add each sender into it. |
| **DMARC** | TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:dmarc@swiftella.co.uk` | Tells inboxes what to do with fakes. Start with `p=none`, move to `p=quarantine` once reports look clean. Banks and lenders are a phishing target, so do move up. |
| **MX** (for replies) | MX | `@` | from Google Workspace / Microsoft 365 | Lets you receive replies at `support@your-domain`. Without it, customers' replies bounce. |

DNS changes take minutes to a few hours. Press **Verify** in the provider's dashboard until DKIM and
Return-Path show green.

## 4. Give the app three settings

On Railway (service → Variables), or in `.env` on your own computer:

```
EMAIL_DOMAIN=swiftella.co.uk
EMAIL_PROVIDER=postmark
EMAIL_API_KEY=<the provider's API key or server token>
```

From these the app sends as `Swiftella Loans <no-reply@swiftella.co.uk>`, with replies going to
`support@swiftella.co.uk`. To change either, set `DEFAULT_FROM_EMAIL` or `LENDER_EMAIL`, keeping them on your domain.

Keep `EMAIL_API_KEY` secret: anyone who has it can send email as you. Don't put it in git or chat.

## 5. Check it works

```bash
python manage.py send_test_email you@example.com
```

On Railway: `railway run python manage.py send_test_email you@example.com`.

Then:

- It should land in the **inbox**, not spam.
- In Gmail, open it → ⋮ → **Show original**. SPF, DKIM and DMARC should all say **PASS**.
- `python manage.py check --deploy` warns if email isn't set up, or if the From address isn't on your domain.

Finally, submit a test application with your own email address and check the confirmation and invoice arrive.
