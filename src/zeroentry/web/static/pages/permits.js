import { api, badge, fmtDT, form, guard, h, isRole, options, pager, qs, table, toast } from '/static/app.js';

export default async function (root) {
  root.append(h('h1', {}, 'Entry permits'),
    h('p', { class: 'muted' }, 'A server decision evaluates current evidence and scope policy. Any positive demonstration is limited to the clearly labelled educational fixture; open a dossier to see exact policy and receipt state.'));

  const filters = { status: '', q: '', offset: 0 };
  const results = h('div');
  const load = guard(async () => {
    const data = await api('GET', '/permits' + qs({ ...filters, limit: 20 }));
    results.replaceChildren(table([
      ['#', (p) => h('a', { href: '/app/permit?id=' + p.permit_id }, p.permit_id)],
      ['Status', (p) => badge(p.status)], ['Manhole', (p) => p.manhole_code], ['Zone', (p) => p.ulb_name],
      ['Contractor', (p) => p.contractor_name || ''], ['Created', (p) => fmtDT(p.created_at)],
      ['Authorised', (p) => fmtDT(p.authorised_at)], ['Valid until', (p) => fmtDT(p.valid_until)],
    ], data.items, 'No permits.'), pager(data, (offset) => { filters.offset = offset; load(); }));
  });

  root.append(h('div', { class: 'panel' }, form([
    { name: 'q', label: 'Manhole code starts with' },
    { name: 'status', label: 'Status', type: 'select', options: ['DRAFT', 'AUTHORISED', 'CLOSED', 'ABORTED', 'CANCELLED'].map((s) => ({ value: s, label: s })) },
  ], async (v) => { Object.assign(filters, { q: v.q || '', status: v.status || '', offset: 0 }); await load(); }, { submit: 'Search' })), results);

  if (isRole('SUPERVISOR')) {
    const jobs = await options('/jobs?method=MANUAL_EXCEPTION&limit=200', (j) => [j.job_id, `Job #${j.job_id} · ${j.manhole_code} · ${j.contractor_name} (${j.status})`]);
    root.append(h('h2', {}, 'Draft a new permit'), h('div', { class: 'panel' },
      h('p', { class: 'muted' }, 'Only jobs with a written mechanisation waiver appear: mechanised cleaning comes first.'),
      form([{ name: 'job_id', label: 'Job', type: 'select', required: true, int: true, options: jobs }],
        async (v) => { const p = await api('POST', '/permits', v); toast('Draft permit #' + p.permit_id + ' created.'); location.assign('/app/permit?id=' + p.permit_id); },
        { submit: 'Create draft permit' })));
  }
  await load();
}
