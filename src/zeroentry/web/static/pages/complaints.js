import { api, badge, fmtDT, form, guard, h, isRole, options, pager, qs, table, toast } from '/static/app.js';

const short = (s, n = 70) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

export default async function (root) {
  root.append(h('h1', {}, 'Complaints'),
    h('p', { class: 'muted' }, 'Blockage complaints against municipal sites. Work is mechanised-first. A waiver records an exception request but cannot override a DENIED or REVIEW_REQUIRED scope policy.'));

  const ulbs = await options('/ulbs?limit=200', (u) => [u.ulb_id, u.name]);
  const filters = { status: '', ulb_id: '', q: '', offset: 0 };
  const results = h('div');

  const load = guard(async () => {
    const data = await api('GET', '/complaints' + qs({ ...filters, limit: 20 }));
    results.replaceChildren(
      table([
        ['#', (c) => h('a', { href: '/app/complaint?id=' + c.complaint_id }, c.complaint_id)],
        ['Manhole', (c) => c.manhole_code], ['Zone', (c) => c.ulb_name], ['Raised', (c) => fmtDT(c.raised_at)],
        ['Status', (c) => badge(c.status)], ['Resolution', (c) => c.resolution_code ? badge(c.resolution_code) : ''],
        ['Description', (c) => short(c.description)],
      ], data.items, 'No complaints match.'),
      pager(data, (offset) => { filters.offset = offset; load(); }));
  });

  root.append(h('div', { class: 'panel' }, form([
    { name: 'q', label: 'Search', hint: 'manhole code or words in the description' },
    { name: 'status', label: 'Status', type: 'select', options: ['OPEN', 'IN_PROGRESS', 'RESOLVED'].map((s) => ({ value: s, label: s })) },
    { name: 'ulb_id', label: 'Zone', type: 'select', options: ulbs },
  ], async (v) => { Object.assign(filters, { q: v.q || '', status: v.status || '', ulb_id: v.ulb_id || '', offset: 0 }); await load(); }, { submit: 'Search' })), results);

  if (isRole('ADMIN', 'ENGINEER')) {
    const manholes = await options('/manholes?limit=200', (m) => [m.manhole_id, `${m.code} · ${m.kind}`]);
    root.append(h('h2', {}, 'Register a complaint'), h('div', { class: 'panel' }, form([
      { name: 'manhole_id', label: 'Manhole', type: 'select', options: manholes, required: true, int: true },
      { name: 'description', label: 'What was reported', type: 'textarea', required: true, wide: true },
    ], async (v) => {
      const c = await api('POST', '/complaints', v);
      toast('Complaint #' + c.complaint_id + ' registered.');
      location.assign('/app/complaint?id=' + c.complaint_id);
    }, { submit: 'Register complaint' })));
  }
  await load();
}
