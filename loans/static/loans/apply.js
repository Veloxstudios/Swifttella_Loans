(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const form = $('apply-form');
  if (!form) return;

  /* ---------- Live quote (same maths as pricing.py and the live calculator) ---------- */
  const p = JSON.parse($('pricing').textContent);
  const gbp = n => new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' }).format(n);
  const pct = n => new Intl.NumberFormat('en-GB', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(n) + '%';
  const amount = $('id_amount');
  const set = (id, v) => { $(id).textContent = v; };

  function updateQuote() {
    const a = Number(amount.value);
    $('amount-label').textContent = gbp(a);
    const pctFilled = (a - amount.min) / (amount.max - amount.min) * 100;
    amount.style.setProperty('--fill', pctFilled + '%');
    if (!(a >= 100 && a <= 1000)) { ['q-amount', 'q-fee', 'q-interest', 'q-charge', 'q-total', 'q-apr'].forEach(i => set(i, '—')); return; }
    const charges = Math.round(Math.min(a * p.dailyRate * p.termDays, a * p.cap) * 100) / 100;
    const fee = Math.min(p.fee, charges);
    const apr = (Math.pow(1 + charges / a, 365 / p.termDays) - 1) * 100;
    set('q-amount', gbp(a)); set('q-interest', gbp(charges - fee)); set('q-fee', gbp(fee));
    set('q-charge', gbp(charges)); set('q-total', gbp(a + charges)); set('q-apr', pct(Math.round(apr * 10) / 10));
  }
  amount.addEventListener('input', updateQuote);
  updateQuote();

  /* ---------- Helpers for filling fields ---------- */
  const POSTCODE = /\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b/i;
  const NI = /\b([A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z])\s?(\d{2})\s?(\d{2})\s?(\d{2})\s?([A-D])\b/i;
  const EMAIL = /[^\s@<>"',;]+@[^\s@<>"',;]+\.[a-z]{2,}/i;
  const PHONE = /(?:\+44\s?\(?0?\)?\s?|\b0)(?:\d[\s-]?){9,10}\b/;
  const SORT = /\b(\d{2})[-\s.](\d{2})[-\s.](\d{2})\b/;
  const ACCOUNT = /\b\d{8}\b/;
  const DATE = /\b(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b/;
  const COUNTRY = /^(united kingdom|uk|u\.k\.|england|scotland|wales|northern ireland|great britain|gb)$/i;

  /* Put values into the usual UK format. */
  const TIDY = {
    postcode: v => postcodeOf(v) || v.toUpperCase(),
    ni_number: v => { const m = v.match(NI); return m ? m.slice(1, 6).join('').toUpperCase() : v.toUpperCase(); },
    sort_code: v => { const d = v.replace(/\D/g, ''); return d.length === 6 ? `${d.slice(0, 2)}-${d.slice(2, 4)}-${d.slice(4)}` : v; },
    account_number: v => v.replace(/\D/g, '').length === 8 ? v.replace(/\D/g, '') : v,
  };

  let filled = [];
  function fill(name, value) {
    const el = form.elements[name];
    if (!el || value === undefined || value === null || String(value).trim() === '') return false;
    value = String(value).trim();
    if (el.tagName === 'SELECT') {
      const want = value.toLowerCase();
      const opt = [...el.options].find(o => o.value && (o.value.toLowerCase() === want || o.text.toLowerCase() === want))
        || [...el.options].find(o => o.value && (o.text.toLowerCase().includes(want) || want.includes(o.text.toLowerCase())));
      if (!opt) return false;
      el.value = opt.value;
    } else {
      el.value = TIDY[name] ? TIDY[name](value) : value;
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    const field = el.closest('.field');
    if (field) { field.classList.remove('just-filled'); void field.offsetWidth; field.classList.add('just-filled'); }
    if (!filled.includes(name)) filled.push(name);
    return true;
  }

  const money = v => String(v).replace(/[£,\s]|gbp|per month|a month|pcm|\/month/gi, '').replace(/[^\d.]/g, '');
  const postcodeOf = s => { const m = s.match(POSTCODE); return m ? (m[1] + ' ' + m[2]).toUpperCase() : ''; };

  function isoDate(s) {
    const m = String(s).match(DATE);
    if (!m) return '';
    const [d, mo, y] = m[4] ? [m[6], m[5], m[4]] : [m[1], m[2], m[3]];
    return `${y}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  }

  /** "10 High Street, Flat 2, London, SW1A 2AA" -> the separate address fields. */
  function splitAddress(text) {
    const postcode = postcodeOf(text);
    let parts = text.replace(POSTCODE, '').split(/[,\n]+/).map(s => s.trim().replace(/\.$/, '')).filter(s => s && !COUNTRY.test(s));
    // "10, High Street" -> "10 High Street"
    if (parts.length > 1 && /^\d+[a-z]?$/i.test(parts[0])) parts = [parts[0] + ' ' + parts[1], ...parts.slice(2)];
    const out = { postcode };
    if (parts.length === 1) out.address_line1 = parts[0];
    if (parts.length === 2) { out.address_line1 = parts[0]; out.town = parts[1]; }
    if (parts.length >= 3) {
      out.address_line1 = parts[0];
      out.town = parts[parts.length - 1];
      out.address_line2 = parts.slice(1, -1).join(', ');
    }
    return out;
  }
  const fillAddress = text => Object.entries(splitAddress(text)).forEach(([k, v]) => fill(k, v));

  function fillName(full) {
    let words = full.trim().split(/\s+/);
    const t = words[0] && words[0].replace(/\.$/, '');
    if (/^(mr|mrs|miss|ms|mx|dr)$/i.test(t)) { fill('title', t[0].toUpperCase() + t.slice(1).toLowerCase()); words = words.slice(1); }
    if (words.length === 1) return fill('first_name', words[0]);
    fill('first_name', words[0]);
    fill('last_name', words.slice(1).join(' '));
  }

  /* Label words people commonly use -> what to do with the value. */
  const LABELS = [
    [/^(full )?name$|^applicant( name)?$|^customer( name)?$/, v => fillName(v)],
    [/^(first|fore|given) ?name$|^forename$/, v => fill('first_name', v)],
    [/^(last|sur|family) ?name$|^surname$/, v => fill('last_name', v)],
    [/^title$/, v => fill('title', v.replace(/\.$/, ''))],
    [/^(dob|d\.o\.b|date of birth|birth ?date|birthday|born)$/, v => fill('date_of_birth', isoDate(v))],
    [/^e-?mail( address)?$/, v => fill('email', v)],
    [/^(phone|mobile|tel|telephone|phone number|mobile number|contact number|number)$/, v => fill('phone', v)],
    [/^(ni|nino|ni ?(no|number)|national insurance( number| no)?)$/, v => fill('ni_number', v)],
    [/^(address|home address|full address|current address|address \(full\))$/, v => fillAddress(v)],
    [/^(address line ?1|street|street address|house|line 1)$/, v => fill('address_line1', v)],
    [/^(address line ?2|line 2|flat)$/, v => fill('address_line2', v)],
    [/^(town|city|town ?\/ ?city|town or city|post ?town)$/, v => fill('town', v)],
    [/^(county|region)$/, v => fill('county', v)],
    [/^(post ?code|zip|zip code)$/, v => fill('postcode', postcodeOf(v) || v)],
    [/^years( at (this |current )?address)?$|^time at address$/, v => fill('years_at_address', v.replace(/[^\d]/g, ''))],
    [/^(employment|employment status|work status|status)$/, v => fill('employment_status', v)],
    [/^(employer|employer name|company|works at)$/, v => fill('employer_name', v)],
    [/^(housing|housing status|residential status|home owner|homeowner)$/, v => fill('housing_status', v)],
    [/^((monthly )?(income|salary|take[- ]home( pay)?|net income|wages))$/, v => fill('monthly_income', money(v))],
    [/^((monthly )?(rent|mortgage|rent ?\/ ?mortgage|rent or mortgage|housing costs?))$/, v => fill('monthly_housing', money(v))],
    [/^((monthly )?(credit|credit repayments|debt|debts|loan repayments))$/, v => fill('monthly_credit', money(v))],
    [/^((monthly )?(other|other spending|bills|outgoings|essential spending|spending))$/, v => fill('monthly_other', money(v))],
    [/^(account (holder|name)|name on (the )?account|account holder name)$/, v => fill('account_holder_name', v)],
    [/^(bank|bank name)$/, v => fill('bank_name', v)],
    [/^(sort ?code|sc)$/, v => fill('sort_code', v)],
    [/^(account ?(number|no)|acc(ount)? ?(no|num)|a\/c( no)?)$/, v => fill('account_number', v.replace(/\D/g, ''))],
    [/^(amount|loan amount|borrow|amount to borrow)$/, v => {
      const n = Math.round(Number(money(v)) / 50) * 50;
      if (n) fill('amount', Math.min(1000, Math.max(100, n)));
    }],
    [/^(purpose|reason|loan purpose|what for)$/, v => fill('purpose', v)],
  ];

  function readPasted(text) {
    filled = [];
    const lines = text.replace(/\r/g, '').split('\n');
    const leftover = [];
    for (let i = 0; i < lines.length; i++) {
      const m = lines[i].match(/^\s*([A-Za-z][A-Za-z .\/()'-]{0,38}?)\s*[:=]\s*(.*)$/);
      const label = m && m[1].toLowerCase().replace(/\s+/g, ' ').trim();
      const rule = label && LABELS.find(([re]) => re.test(label));
      if (!rule) { leftover.push(lines[i]); continue; }
      let value = m[2].trim();
      // An "Address:" label followed by lines of address underneath it.
      if (/address/.test(label) && rule[1] === LABELS[8][1]) {
        while (i + 1 < lines.length && lines[i + 1].trim() && !/^\s*[A-Za-z][A-Za-z .\/()'-]{0,38}?\s*[:=]/.test(lines[i + 1])) {
          value += (value ? '\n' : '') + lines[++i].trim();
          if (POSTCODE.test(lines[i])) break;
        }
      }
      if (value) rule[1](value);
    }

    // Anything without a label: pick out the values we can recognise on sight.
    let rest = leftover.join('\n');
    const take = (re, name, fn) => {
      if (filled.includes(name)) return;
      const m = rest.match(re);
      if (!m) return;
      if (fill(name, fn ? fn(m) : m[0])) rest = rest.replace(m[0], ' ');
    };
    take(EMAIL, 'email');
    take(NI, 'ni_number', m => m.slice(1, 6).join('').toUpperCase());
    take(DATE, 'date_of_birth', m => isoDate(m[0]));
    take(SORT, 'sort_code', m => `${m[1]}-${m[2]}-${m[3]}`);
    take(PHONE, 'phone');
    take(ACCOUNT, 'account_number');
    // A line that is just two to four words, like "Jane Smith", near the top is probably the name.
    if (!filled.includes('first_name')) {
      const nameLine = rest.split('\n').map(s => s.trim()).filter(Boolean)[0];
      if (nameLine && /^((mr|mrs|miss|ms|mx|dr)\.?\s+)?[A-Za-z'’-]+(\s+[A-Za-z'’-]+){1,3}$/i.test(nameLine) && !/\b(street|road|lane|avenue|close|drive|flat)\b/i.test(nameLine)) {
        fillName(nameLine);
        rest = rest.replace(nameLine, ' ');
      }
    }
    if (!filled.includes('postcode')) {
      const restLines = rest.split('\n').map(s => s.trim());
      const at = restLines.findIndex(l => POSTCODE.test(l));
      if (at >= 0) {
        // Use the postcode line plus the address lines just above it.
        let start = at;
        while (start > 0 && restLines[start - 1] && !/[:=@]/.test(restLines[start - 1]) && at - start < 4) start--;
        fillAddress(restLines.slice(start, at + 1).join('\n'));
      }
    }
    return filled.length;
  }

  const status = $('paste-status');
  $('paste-fill').addEventListener('click', () => {
    const text = $('paste-box').value;
    if (!text.trim()) { status.textContent = 'Paste your details into the box first.'; status.className = 'paste-status is-warn'; return; }
    const n = readPasted(text);
    if (n) {
      status.textContent = `Filled ${n} field${n === 1 ? '' : 's'}. Please check them below.`;
      status.className = 'paste-status is-ok';
      const first = form.elements[filled[0]];
      if (first) first.closest('fieldset').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      status.textContent = "We couldn't recognise any details. Try putting each one on its own line, like \"Email: you@example.com\".";
      status.className = 'paste-status is-warn';
    }
  });
  $('paste-clear').addEventListener('click', () => { $('paste-box').value = ''; status.textContent = ''; $('paste-box').focus(); });

  /* Paste a whole address straight into "Address line 1" and it is split up. */
  const line1 = form.elements.address_line1;
  line1.addEventListener('paste', e => {
    const text = (e.clipboardData || window.clipboardData).getData('text');
    if (!/[,\n]/.test(text.trim()) && !POSTCODE.test(text)) return; // a normal single line: let it paste
    e.preventDefault();
    filled = [];
    fillAddress(text);
  });

  /* Tidy common formats as people leave each box. */
  Object.entries(TIDY).forEach(([name, fn]) => form.elements[name] &&
    form.elements[name].addEventListener('blur', e => { e.target.value = fn(e.target.value); }));
})();
