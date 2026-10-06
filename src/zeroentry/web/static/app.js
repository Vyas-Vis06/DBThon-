// ZeroEntry UI core: API client, DOM helpers, navigation. No framework, no build step, nothing loaded from a CDN.
// Every piece of user data is inserted as a TEXT NODE (never parsed as an HTML string), so stored text can never become markup (XSS).
// tests/api/test_web.py fails the build if an HTML-string API is ever introduced.
// Authorisation is NOT decided here: hiding a button is cosmetic; the server refuses what a role may not do.

export const state = { user: null, csrf: null };

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    Object.assign(this, { status, code, details });
  }
}

export async function api(method, path, body) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET' && state.csrf) headers['X-CSRF-Token'] = state.csrf;
  const res = await fetch('/api/v1' + path, {
    method, headers, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch { /* empty or non-JSON body */ }
  if (res.status === 401 && !location.pathname.endsWith('/login')) {
    location.assign('/app/login');
    throw new ApiError(401, 'unauthorized', 'Please sign in again.');
  }
  if (!res.ok) throw new ApiError(res.status, data?.error?.code, data?.error?.message || res.statusText, data?.error?.details);
  return data;
}

export const qs = (params) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) if (v !== undefined && v !== null && v !== '') p.set(k, v);
  const s = p.toString();
  return s ? '?' + s : '';
};

// ---- DOM ---------------------------------------------------------------------------------------------------------
export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === undefined || kid === null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const KIND = {
  OK: 'ok', AUTHORISED: 'ok', RESOLVED: 'ok', ACTIVE: 'ok', APPROVED: 'ok', PAID: 'ok', COMPLETED: 'ok', CLEARED: 'ok', MECHANISED: 'ok', CLOSED: 'grey',
  OPEN: 'info', SUBMITTED: 'info', NEAR_MISS: 'info', IN_PROGRESS: 'warn', PLANNED: 'grey', DRAFT: 'grey', CANCELLED: 'grey', DISMISSED: 'grey',
  EVIDENCE_RECEIVED: 'warn', SUSPENDED: 'warn', PARTIAL: 'warn', DISABILITY: 'warn', MANUAL_EXCEPTION: 'warn',
  ABORTED: 'bad', CONFIRMED: 'bad', BLACKLISTED: 'bad', FATALITY: 'bad', FAILED: 'bad', REJECTED: 'bad',
};
export const badge = (text, kind) => h('span', { class: 'badge ' + (kind || KIND[text] || 'grey') }, String(text ?? '').replaceAll('_', ' '));

export function toast(message, kind = 'ok') {
  const el = h('div', { class: 'toast ' + kind }, message);
  document.getElementById('toasts').append(el);
  setTimeout(() => el.remove(), kind === 'bad' ? 9000 : 4500);
}

// Run an async handler; show failures as a toast instead of an unhandled rejection. The server's message is the
// database's own wording for rule violations, so it is shown verbatim.
export const guard = (fn) => async (...args) => {
  try { return await fn(...args); } catch (e) { toast(e.message || String(e), 'bad'); }
};

// ---- formatting (India Standard Time, the zone the statutory rules are evaluated in) ----------------------------------
const IST = 'Asia/Kolkata';
export const fmtDT = (iso) => iso ? new Date(iso).toLocaleString('en-IN', { timeZone: IST, dateStyle: 'medium', timeStyle: 'short' }) : '';
export const fmtDate = (d) => d ? new Date(d + (String(d).length === 10 ? 'T00:00:00+05:30' : '')).toLocaleDateString('en-IN', { timeZone: IST, dateStyle: 'medium' }) : '';
export const money = (n) => (n === null || n === undefined) ? '' : '₹ ' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
export const ago = (iso) => { const m = Math.round((Date.now() - new Date(iso)) / 60000); return m < 1 ? 'just now' : m < 90 ? m + ' min ago' : Math.round(m / 60) + ' h ago'; };
// <input type=datetime-local> holds a wall-clock time with no zone; the UI treats it as India time.
export const toIso = (local) => (local.length === 16 ? local + ':00' : local) + '+05:30';   // 16 = minutes only, 19 = with seconds
// Wall-clock India time as a datetime-local value WITH seconds (minute precision could round "now" down to before an
// instant that just happened, such as the authorisation of a permit).
export const localIST = (date) => new Date(date.getTime() + 330 * 60000).toISOString().slice(0, 19);
export const nowLocalIST = (plusMinutes = 0) => localIST(new Date(Date.now() + plusMinutes * 60000));

// ---- widgets -----------------------------------------------------------------------------------------------------------
export function table(columns, rows, empty = 'Nothing to show.') {
  if (!rows || rows.length === 0) return h('p', { class: 'muted' }, empty);
  return h('div', { class: 'scroll' }, h('table', {},
    h('thead', {}, h('tr', {}, columns.map(([label]) => h('th', { scope: 'col' }, label)))),
    h('tbody', {}, rows.map((row) => h('tr', {}, columns.map(([, cell, cls]) => h('td', { class: cls }, cell(row))))))));
}

export function kv(pairs) {
  return h('dl', { class: 'grid' }, pairs.filter(Boolean).map(([k, v]) => h('div', { class: 'tile' }, h('div', { class: 'l' }, k), h('div', {}, v ?? '–'))));
}

// field: {name,label,type,options,required,value,hint,wide,step,min,max,int,attrs}
export function form(fields, onSubmit, { submit = 'Save', danger = false } = {}) {
  const el = h('form', { class: 'fields', novalidate: false });
  for (const f of fields) {
    let input;
    const common = { name: f.name, id: undefined, required: !!f.required, ...(f.attrs || {}) };
    switch (f.type) {
      case 'textarea': input = h('textarea', { ...common, maxlength: f.max || 2000, placeholder: f.placeholder }, f.value || ''); break;
      case 'select':
        input = h('select', common, !f.required && h('option', { value: '' }, '—'),
          (f.options || []).map((o) => h('option', { value: o.value, selected: String(o.value) === String(f.value) }, o.label)));
        break;
      case 'checkbox': input = h('input', { ...common, type: 'checkbox', checked: !!f.value }); break;
      case 'datetime': input = h('input', { ...common, type: 'datetime-local', step: '1', value: f.value === 'now' ? nowLocalIST() : f.value }); break;
      case 'number': input = h('input', { ...common, type: 'number', step: f.step || 'any', min: f.min, max: f.max, value: f.value }); break;
      default: input = h('input', { ...common, type: f.type || 'text', value: f.value, placeholder: f.placeholder, maxlength: f.max, minlength: f.minlength });
    }
    if (f.type === 'checkbox') el.append(h('label', { class: 'check' + (f.wide ? ' wide' : '') }, input, f.label));
    else el.append(h('label', { class: f.wide ? 'wide' : '' }, f.label, input, f.hint && h('span', { class: 'hint' }, f.hint)));
  }
  const button = h('button', { type: 'submit', class: danger ? 'danger' : 'primary' }, submit);
  el.append(h('div', { class: 'wide' }, button));
  el.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const values = {};
    for (const f of fields) {
      const control = el.elements[f.name];
      let v = f.type === 'checkbox' ? control.checked : control.value;
      if (v === '' && f.type !== 'checkbox') continue;                  // empty = not sent (the server applies its default)
      if (f.type === 'number' || f.int) v = Number(v);
      if (f.type === 'datetime') v = toIso(v);
      values[f.name] = v;
    }
    button.disabled = true;
    try { await onSubmit(values, el); } catch (e) { toast(e.message || String(e), 'bad'); } finally { button.disabled = false; }
  });
  return el;
}

export function tabs(items, initial) {
  const bar = h('div', { class: 'tabs', role: 'tablist' });
  const panel = h('div', { role: 'tabpanel' });
  const buttons = {};
  const select = async (id) => {
    for (const [k, b] of Object.entries(buttons)) b.setAttribute('aria-selected', String(k === id));
    panel.replaceChildren(h('p', { class: 'muted' }, 'Loading…'));
    const item = items.find((i) => i.id === id);
    const content = h('div');
    try { await item.render(content); } catch (e) { content.replaceChildren(h('p', { class: 'banner bad' }, e.message)); }
    panel.replaceChildren(content);
    history.replaceState(null, '', '#' + id);
  };
  for (const item of items) {
    buttons[item.id] = h('button', { type: 'button', role: 'tab', 'aria-selected': 'false', onclick: () => select(item.id) }, item.label);
    bar.append(buttons[item.id]);
  }
  const start = items.some((i) => i.id === location.hash.slice(1)) ? location.hash.slice(1) : (initial || items[0].id);
  queueMicrotask(() => select(start));
  return h('div', {}, bar, panel);
}

export function pager(data, onChange) {
  const { total, limit, offset } = data;
  const last = Math.min(offset + limit, total);
  return h('div', { class: 'row between small' },
    h('span', { class: 'muted' }, total ? `${offset + 1}–${last} of ${total}` : 'No results'),
    h('span', { class: 'row' },
      h('button', { type: 'button', disabled: offset === 0, onclick: () => onChange(Math.max(0, offset - limit)) }, '← Previous'),
      h('button', { type: 'button', disabled: last >= total, onclick: () => onChange(offset + limit) }, 'Next →')));
}

export async function options(path, mapper) {
  const data = await api('GET', path);
  return (data.items || data).map((row) => { const [value, label] = mapper(row); return { value, label }; });
}

// The red/green checklist: one row per legal clause, with the clause's legal reference and the database's explanation.
export function clauseList(clauses) {
  return h('ul', { class: 'clauses' }, clauses.map((c) => h('li', { class: 'clause ' + (c.passed ? 'pass' : 'fail') },
    h('span', { class: 'icon', 'aria-hidden': 'true' }, c.passed ? '✓' : '✗'),
    h('div', {}, h('strong', {}, c.title), ' ', h('span', { class: 'badge ' + (c.passed ? 'ok' : 'bad') }, c.passed ? 'PASS' : 'FAIL'),
      h('div', { class: 'detail' }, c.detail), h('div', { class: 'ref' }, c.legal_ref)))));
}

export const isRole = (...roles) => roles.includes(state.user?.role);

// ---- navigation and boot ---------------------------------------------------------------------------------------------
const STAFF = ['ADMIN', 'ENGINEER', 'SUPERVISOR', 'AUDITOR'];
const NAV = [
  ['dashboard', 'Dashboard', null],
  ['complaints', 'Complaints', STAFF],
  ['permits', 'Permits', [...STAFF, 'CONTRACTOR', 'WORKER']],
  ['shadow', 'Shadow entries', ['ADMIN', 'ENGINEER', 'AUDITOR']],
  ['incidents', 'Incidents & compensation', [...STAFF, 'CONTRACTOR']],
  ['invoices', 'Invoices & holds', [...STAFF, 'CONTRACTOR']],
  ['registry', 'Registry', [...STAFF, 'CONTRACTOR', 'WORKER']],
  ['reports', 'Reports', ['ADMIN', 'ENGINEER', 'AUDITOR']],
  ['admin', 'Admin', ['ADMIN', 'AUDITOR']],
];

function renderChrome(page) {
  const nav = document.getElementById('nav');
  const who = document.getElementById('who');
  nav.replaceChildren();
  who.replaceChildren();
  if (!state.user) return;
  for (const [id, label, roles] of NAV) {
    if (roles && !roles.includes(state.user.role)) continue;
    nav.append(h('a', { href: '/app/' + id, 'aria-current': id === page ? 'page' : undefined }, label));
  }
  who.append(h('span', {}, state.user.full_name, ' · ', badge(state.user.role, 'info')),
    h('button', { type: 'button', onclick: guard(async () => { await api('POST', '/auth/logout'); location.assign('/app/login'); }) }, 'Sign out'));
}

async function boot() {
  const page = location.pathname.split('/')[2] || 'dashboard';
  const main = document.getElementById('main');
  if (!/^[a-z_]+$/.test(page)) { main.replaceChildren(h('h1', {}, 'Page not found')); return; }
  document.title = 'ZeroEntry · ' + page;
  if (page !== 'login') {
    try {
      const me = await api('GET', '/auth/me');
      state.user = me.user;
      state.csrf = me.csrf_token;
    } catch { return; }                                   // api() already redirected to the sign-in page
  }
  renderChrome(page);
  let module;
  try { module = await import(`/static/pages/${page}.js`); } catch { main.replaceChildren(h('h1', {}, 'Page not found'), h('p', {}, 'There is no such screen.')); return; }
  main.replaceChildren();
  try { await module.default(main, { user: state.user, params: new URLSearchParams(location.search) }); }
  catch (e) { main.append(h('p', { class: 'banner bad' }, e.message || String(e))); }
  main.focus();
}

window.addEventListener('unhandledrejection', (ev) => { toast(ev.reason?.message || 'Something went wrong.', 'bad'); });
boot();
