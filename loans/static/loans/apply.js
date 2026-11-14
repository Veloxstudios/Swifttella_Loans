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

  /* Small "Paste" button beside each text box: pastes from the clipboard into that one field. */
  const PASTE_SKIP = ['checkbox', 'radio', 'range', 'hidden', 'file', 'submit', 'button', 'password'];
  function applyPaste(el, text) {
    text = text.trim();
    if (!text) return false;
    const name = el.name;
    if (name === 'address_line1' && (/[,\n]/.test(text) || POSTCODE.test(text))) { fillAddress(text); return true; }
    if (name === 'first_name' && /\s/.test(text) && !form.elements.last_name.value) { fillName(text); return true; }
    if (name === 'date_of_birth') return fill(name, isoDate(text) || text);
    if (el.type === 'number' || /^monthly_/.test(name)) return fill(name, money(text) || text);
    return fill(name, text.split('\n')[0]);
  }
  [...form.elements].forEach(el => {
    if (el.tagName !== 'INPUT' || PASTE_SKIP.includes(el.type) || !el.name) return;
    const row = document.createElement('div');
    row.className = 'input-row';
    el.parentNode.insertBefore(row, el);
    row.appendChild(el);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'paste-btn';
    btn.textContent = 'Paste';
    btn.setAttribute('aria-label', 'Paste into ' + ((form.querySelector('label[for="' + el.id + '"]') || {}).textContent || el.name).replace(/\(optional\)/, '').trim());
    btn.addEventListener('click', async () => {
      let ok = false;
      try { ok = applyPaste(el, await navigator.clipboard.readText()); } catch (e) { /* blocked: fall through */ }
      if (!ok) { el.focus(); btn.textContent = 'Press Ctrl+V'; setTimeout(() => { btn.textContent = 'Paste'; }, 2200); }
    });
    /* The Paste button stays tucked away behind a small "<" tab; clicking it slides the button out. */
    const reveal = document.createElement('div');
    reveal.className = 'paste-reveal';
    reveal.appendChild(btn);
    btn.tabIndex = -1;
    const tab = document.createElement('button');
    tab.type = 'button';
    tab.className = 'paste-tab';
    tab.textContent = '<';
    tab.setAttribute('aria-expanded', 'false');
    tab.setAttribute('aria-label', 'Show paste button');
    tab.addEventListener('click', () => {
      const open = row.classList.toggle('is-open');
      tab.setAttribute('aria-expanded', String(open));
      tab.setAttribute('aria-label', open ? 'Hide paste button' : 'Show paste button');
      btn.tabIndex = open ? 0 : -1;
    });
    row.appendChild(reveal);
    row.appendChild(tab);
  });

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
