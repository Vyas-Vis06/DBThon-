import { api, badge, fmtDT, form, guard, h, isRole, money, options, pager, qs, table, tabs, toast } from '/static/app.js';

export default async function (root) {
  const officer = isRole('ADMIN', 'ENGINEER');
  root.append(h('h1', {}, 'Invoices and holds'),
    h('p', { class: 'muted' }, 'An invoice on hold can be neither approved nor paid. Each hold records its source (a shadow-entry alert or an incident) and is released only by that source.'));

  const invoicesTab = async (box) => {
    const filters = { status: '', on_hold: '', offset: 0 };
    const results = h('div');
    const act = (inv, verb, label, cls) => h('button', { type: 'button', class: cls || '', onclick: guard(async () => { await api('POST', `/invoices/${inv.invoice_id}/${verb}`); toast(label + ': done.'); load(); }) }, label);
    const load = guard(async () => {
      const data = await api('GET', '/invoices' + qs({ ...filters, limit: 20 }));
      results.replaceChildren(table([['No.', (i) => i.invoice_no], ['Job', (i) => '#' + i.job_id], ['Amount', (i) => money(i.amount_inr)], ['Submitted', (i) => fmtDT(i.submitted_at)],
        ['Status', (i) => badge(i.status)], ['Hold', (i) => i.on_hold ? badge('ON HOLD: ' + i.hold_reasons.replaceAll('_', ' '), 'bad') : 'no'],
        ['', (i) => !officer ? '' : h('span', { class: 'row' },
          i.status === 'SUBMITTED' && [act(i, 'approve', 'Approve', 'primary'), act(i, 'reject', 'Reject', 'danger')], i.status === 'APPROVED' && [act(i, 'pay', 'Mark paid', 'primary'), act(i, 'reject', 'Reject', 'danger')])]],
        data.items, 'No invoices.'), pager(data, (o) => { filters.offset = o; load(); }));
    });
    box.append(h('div', { class: 'panel' }, form([
      { name: 'status', label: 'Status', type: 'select', options: ['SUBMITTED', 'APPROVED', 'PAID', 'REJECTED'].map((s) => ({ value: s, label: s })) },
      { name: 'on_hold', label: 'Holds', type: 'select', options: [{ value: 'true', label: 'Only invoices on hold' }, { value: 'false', label: 'Only invoices not on hold' }] },
    ], async (v) => { Object.assign(filters, { status: v.status || '', on_hold: v.on_hold || '', offset: 0 }); await load(); }, { submit: 'Filter' })), results);

    if (officer || isRole('CONTRACTOR')) {
      const jobs = await options('/jobs?limit=200', (j) => [j.job_id, `Job #${j.job_id} · ${j.manhole_code} · ${j.contractor_name}`]);
      box.append(h('h2', {}, 'Submit an invoice'), h('div', { class: 'panel' }, form([
        { name: 'job_id', label: 'Job', type: 'select', required: true, int: true, options: jobs },
        { name: 'invoice_no', label: 'Invoice number', required: true }, { name: 'amount_inr', label: 'Amount (₹)', type: 'number', step: '0.01', min: 0.01, required: true },
      ], async (v) => {
        const r = await api('POST', '/invoices', v);
        toast(r.on_hold ? 'Invoice submitted, but it is ON HOLD because of an alert or incident on this job.' : 'Invoice submitted.', r.on_hold ? 'bad' : 'ok');
        load();
      }, { submit: 'Submit invoice' })));
    }
    await load();
  };

  const holdsTab = async (box) => {
    const data = await api('GET', '/invoice-holds?limit=100');
    box.append(table([['Invoice', (x) => `${x.invoice_no} (${money(x.amount_inr)})`], ['Reason', (x) => badge(x.reason, 'bad')], ['Source', (x) => x.alert_id ? 'alert #' + x.alert_id : 'incident #' + x.incident_id],
      ['Placed', (x) => fmtDT(x.placed_at)],
      ['', (x) => x.reason === 'SHADOW_ENTRY' ? h('span', { class: 'small muted' }, 'released by dismissing its alert') : (officer ? h('details', {}, h('summary', {}, 'Release'), form([
        { name: 'note', label: 'Written reason (10+ characters)', type: 'textarea', required: true, wide: true, attrs: { minlength: 10 } }],
        async (v) => { await api('POST', `/invoice-holds/${x.hold_id}/release`, v); toast('Hold released.'); location.reload(); }, { submit: 'Release hold' })) : '')]],
      data.items, 'No active holds.'));
  };

  const items = [{ id: 'invoices', label: 'Invoices', render: invoicesTab }];
  if (isRole('ADMIN', 'ENGINEER', 'AUDITOR')) items.push({ id: 'holds', label: 'Active holds', render: holdsTab });
  root.append(tabs(items));
}
