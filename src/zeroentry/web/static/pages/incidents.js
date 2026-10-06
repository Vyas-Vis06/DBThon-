import { api, badge, fmtDT, form, guard, h, isRole, kv, money, options, pager, qs, table, tabs, toast } from '/static/app.js';

export default async function (root) {
  const recorder = isRole('ADMIN', 'ENGINEER', 'SUPERVISOR');
  const payer = isRole('ADMIN', 'ENGINEER');
  root.append(h('h1', {}, 'Incidents and compensation'),
    h('p', { class: 'muted' }, 'Recording a fatality is ONE atomic transaction: the incident, a ₹30-lakh compensation case with a deadline, the contractor’s blacklisting, the stop-work on the job’s permits and the hold on its invoices all happen together, or not at all.'));

  const incidentsTab = async (box) => {
    const filters = { incident_type: '', offset: 0 };
    const results = h('div');
    const load = guard(async () => {
      const data = await api('GET', '/incidents' + qs({ ...filters, limit: 20 }));
      results.replaceChildren(table([['#', (i) => i.incident_id], ['Type', (i) => badge(i.incident_type)], ['Occurred', (i) => fmtDT(i.occurred_at)], ['Worker', (i) => i.worker_name || ''],
        ['Contractor', (i) => i.contractor_name], ['Manhole', (i) => `${i.manhole_code} · ${i.ulb_name}`],
        ['Permit', (i) => i.permit_id ? h('a', { href: '/app/permit?id=' + i.permit_id }, '#' + i.permit_id) : badge('NO PERMIT', 'bad')], ['What happened', (i) => i.description]],
        data.items, 'No incidents recorded.'), pager(data, (o) => { filters.offset = o; load(); }));
    });
    box.append(h('div', { class: 'panel' }, form([{ name: 'incident_type', label: 'Type', type: 'select', options: ['FATALITY', 'DISABILITY', 'NEAR_MISS'].map((t) => ({ value: t, label: t })) }],
      async (v) => { filters.incident_type = v.incident_type || ''; filters.offset = 0; await load(); }, { submit: 'Filter' })), results);
    await load();
  };

  const casesTab = async (box) => {
    const filters = { status: '', overdue: '', offset: 0 };
    const results = h('div');
    const load = guard(async () => {
      const data = await api('GET', '/compensation-cases' + qs({ ...filters, limit: 20 }));
      results.replaceChildren(table([['Case', (c) => c.case_id], ['Contractor', (c) => c.contractor_name], ['Incident', (c) => badge(c.incident_type)], ['Due', (c) => money(c.amount_due)],
        ['Paid', (c) => money(c.amount_paid)], ['Due by', (c) => c.due_by], ['Status', (c) => badge(c.status)],
        ['', (c) => (payer && c.status !== 'PAID') ? h('details', {}, h('summary', {}, 'Record payment'), form([{ name: 'amount', label: 'Amount (₹)', type: 'number', step: '0.01', required: true, min: 0.01 }],
          async (v) => { await api('POST', `/compensation-cases/${c.case_id}/payments`, v); toast('Payment recorded.'); load(); }, { submit: 'Record payment' })) : '']],
        data.items, 'No compensation cases.'), pager(data, (o) => { filters.offset = o; load(); }));
    });
    box.append(h('div', { class: 'panel' }, form([
      { name: 'status', label: 'Status', type: 'select', options: ['OPEN', 'PARTIAL', 'PAID'].map((s) => ({ value: s, label: s })) },
      { name: 'overdue', label: 'Only overdue', type: 'select', options: [{ value: 'true', label: 'Yes: unpaid and past the deadline' }] },
    ], async (v) => { Object.assign(filters, { status: v.status || '', overdue: v.overdue || '', offset: 0 }); await load(); }, { submit: 'Filter' })), results);
    await load();
  };

  const recordTab = async (box) => {
    if (!recorder) { box.append(h('p', { class: 'muted' }, 'Only a supervisor, engineer or administrator can record an incident.')); return; }
    const workers = await options('/workers?limit=200', (w) => [w.worker_id, `${w.full_name} · ${w.namaste_id}`]);
    const manholes = await options('/manholes?limit=200', (m) => [m.manhole_id, m.code]);
    const outcome = h('div');
    box.append(h('p', { class: 'muted' }, 'Link the permit if there was one. A death with NO permit is itself evidence of a shadow entry, and still triggers every consequence.'),
      form([
        { name: 'incident_type', label: 'Type', type: 'select', required: true, options: ['FATALITY', 'DISABILITY', 'NEAR_MISS'].map((t) => ({ value: t, label: t })) },
        { name: 'occurred_at', label: 'Occurred (India time)', type: 'datetime', value: 'now', required: true },
        { name: 'worker_id', label: 'Worker', type: 'select', required: true, int: true, options: workers },
        { name: 'manhole_id', label: 'Manhole', type: 'select', required: true, int: true, options: manholes },
        { name: 'permit_id', label: 'Permit # (if any)', type: 'number', step: '1', min: 1 },
        { name: 'job_id', label: 'Job # (if known)', type: 'number', step: '1', min: 1 },
        { name: 'description', label: 'What happened', type: 'textarea', required: true, wide: true },
      ], async (v) => {
        if (v.incident_type === 'FATALITY' && !confirm('Recording a FATALITY blacklists the contractor, aborts the job’s permits and holds its invoices, all at once. Continue?')) return;
        const r = await api('POST', '/incidents', v);
        outcome.replaceChildren(h('p', { class: 'banner ok' }, `Incident #${r.incident_id} recorded in one transaction.`), kv([
          ['Compensation case', r.compensation_case ? `${money(r.compensation_case.amount_due)} due by ${r.compensation_case.due_by}` : 'none (near miss)'],
          ['Contractor', `${r.contractor.name}: ${r.contractor.status}`], ['Invoices held', r.invoice_holds.length ? String(r.invoice_holds.length) : 'none visible to you'],
          ['Permit', r.permit_id ? h('a', { href: '/app/permit?id=' + r.permit_id }, '#' + r.permit_id + ' (aborted if it was authorised)') : 'no permit linked']]));
      }, { submit: 'Record incident', danger: true }), outcome);
  };

  root.append(tabs([{ id: 'incidents', label: 'Incidents', render: incidentsTab }, { id: 'cases', label: 'Compensation cases', render: casesTab },
    { id: 'overdue', label: 'Overdue', render: async (box) => {
      const data = await api('GET', '/compensation-cases?overdue=true&limit=100');
      box.append(h('p', { class: 'muted' }, 'Unpaid cases past their deadline (view v_compensation_overdue).'),
        table([['Case', (c) => c.case_id], ['Contractor', (c) => c.contractor_name], ['Outstanding', (c) => money(c.amount_due - c.amount_paid)], ['Was due', (c) => c.due_by],
          ['Status', (c) => badge(c.status)]], data.items, 'Nothing overdue.'));
    } }, { id: 'record', label: 'Record an incident', render: recordTab }]));
}
