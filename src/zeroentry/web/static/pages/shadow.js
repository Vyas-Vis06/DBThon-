import { api, badge, fmtDT, form, guard, h, isRole, pager, qs, table, tabs, toast } from '/static/app.js';

const short = (s, n = 90) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

export default async function (root) {
  const decider = isRole('ADMIN', 'ENGINEER');
  root.append(h('h1', {}, 'Shadow-entry detection by absence'),
    h('div', { class: 'panel' },
      h('p', {}, 'A shadow entry is a human entry nobody recorded. It cannot be seen directly, so the database looks for the records that a lawful clearance would have left behind.'),
      h('ul', {},
        h('li', {}, h('strong', {}, 'SE1:'), ' a complaint closed as “cleared” with no machine clearance and no authorised, closed permit with a logged entry, recorded within the grace window.'),
        h('li', {}, h('strong', {}, 'SE2:'), ' a closed permit with an entrant who has no entry log.')),
      h('p', { class: 'muted small' }, 'Evidence recorded late never closes an alert on its own: it sends the alert to a person. Exempt resolutions (duplicate, no blockage, referred, withdrawn) are never flagged.'),
      decider && h('div', { class: 'row' }, h('button', { type: 'button', class: 'primary', onclick: guard(async () => {
        const r = await api('POST', '/detections/scan');
        toast(`Scan complete: ${r.opened} alert(s) opened, ${r.moved_to_review} sent to review, ${r.pending_in_grace} still inside the grace window.`);
        setTimeout(() => location.reload(), 1200);
      }) }, 'Run the absence scan now'), h('span', { class: 'small muted' }, 'Safe to repeat: results are idempotent (one alert per complaint and rule).'))));

  const detail = h('div');

  async function openAlert(id) {
    const a = await api('GET', `/detections/alerts/${id}`);
    const open = a.status === 'OPEN' || a.status === 'EVIDENCE_RECEIVED';
    detail.replaceChildren(h('div', { class: 'panel' },
      h('div', { class: 'row between' }, h('h2', {}, `Alert #${a.alert_id} `, badge(a.status), ' ', badge(a.rule_code.split('_')[0], 'info')), h('button', { type: 'button', onclick: () => detail.replaceChildren() }, 'Close')),
      h('p', {}, a.reason),
      h('p', { class: 'small muted' }, `Evidence deadline ${fmtDT(a.evidence_deadline)} · detected ${fmtDT(a.detected_at)} · complaint `, h('a', { href: '/app/complaint?id=' + a.complaint_id }, '#' + a.complaint_id)),
      h('h3', {}, 'History (append-only)'),
      h('ul', { class: 'timeline' }, a.events.map((e) => h('li', {}, h('strong', {}, `${e.from_status || '∅'} → ${e.to_status}`), ' · ', fmtDT(e.occurred_at), e.note && h('div', { class: 'small muted' }, e.note)))),
      h('h3', {}, 'Invoices held because of this alert'),
      table([['Invoice', (x) => x.invoice_no], ['Amount', (x) => '₹ ' + Number(x.amount_inr).toLocaleString('en-IN')], ['Placed', (x) => fmtDT(x.placed_at)],
        ['Released', (x) => x.released_at ? fmtDT(x.released_at) : badge('HELD', 'warn')]], a.holds, 'No unpaid invoice was on these jobs.'),
      a.review_note && h('p', {}, h('strong', {}, 'Decision: '), a.review_note),
      (open && decider) ? [h('h3', {}, 'Decide'), h('p', { class: 'small muted' }, 'Confirming keeps the invoice holds; dismissing (a false positive) releases exactly this alert’s holds. A written note is required and the decision is final.'),
        form([
          { name: 'decision', label: 'Decision', type: 'select', required: true, options: [{ value: 'CONFIRMED', label: 'CONFIRMED: an unrecorded entry is likely' }, { value: 'DISMISSED', label: 'DISMISSED: false positive' }] },
          { name: 'note', label: 'Written reason (10+ characters)', type: 'textarea', required: true, wide: true, attrs: { minlength: 10 } },
        ], async (v) => { await api('POST', `/detections/alerts/${a.alert_id}/review`, v); toast('Decision recorded.'); location.reload(); }, { submit: 'Record decision' })]
        : open ? h('p', { class: 'muted small' }, 'Only an engineer or administrator can decide an alert.') : null));
    detail.scrollIntoView({ behavior: 'smooth' });
  }

  const alertsTab = async (box) => {
    const filters = { status: '', offset: 0 };
    const results = h('div');
    const load = guard(async () => {
      const data = await api('GET', '/detections/alerts' + qs({ ...filters, limit: 20 }));
      results.replaceChildren(table([
        ['#', (a) => h('button', { type: 'button', class: 'link', onclick: () => openAlert(a.alert_id) }, a.alert_id)], ['Status', (a) => badge(a.status)], ['Rule', (a) => a.rule_title],
        ['Manhole', (a) => `${a.manhole_code} · ${a.ulb_name}`], ['Contractor', (a) => a.contractor_name || 'no job at all'], ['Detected', (a) => fmtDT(a.detected_at)],
        ['Why', (a) => short(a.reason)]], data.items, 'No alerts. Run the scan, or nothing is missing.'), pager(data, (o) => { filters.offset = o; load(); }));
    });
    box.append(h('div', { class: 'panel' }, form([{ name: 'status', label: 'Status', type: 'select',
      options: ['OPEN', 'EVIDENCE_RECEIVED', 'CONFIRMED', 'DISMISSED'].map((s) => ({ value: s, label: s })) }],
      async (v) => { filters.status = v.status || ''; filters.offset = 0; await load(); }, { submit: 'Filter' })), results);
    await load();
  };

  const candidatesTab = async (box) => {
    const data = await api('GET', '/detections/candidates?limit=100');
    box.append(h('p', { class: 'muted' }, 'Everything currently missing its expected evidence, including items still inside the grace window (pending: the records may yet arrive).'),
      table([['Rule', (c) => c.rule_code.split('_')[0]], ['Complaint', (c) => h('a', { href: '/app/complaint?id=' + c.complaint_id }, '#' + c.complaint_id)],
        ['Anchor event', (c) => fmtDT(c.anchor_at)], ['Evidence deadline', (c) => fmtDT(c.evidence_deadline)],
        ['State', (c) => c.past_grace ? badge('PAST GRACE', 'bad') : badge('PENDING', 'warn')], ['Late evidence', (c) => c.late_evidence_exists ? badge('YES', 'warn') : 'no'],
        ['Alert', (c) => c.alert_id ? [h('a', { href: '#alerts', onclick: () => openAlert(c.alert_id) }, '#' + c.alert_id), ' ', badge(c.alert_status)] : '–'],
        ['Why', (c) => short(c.reason, 110)]], data.items, 'Nothing is missing.'));
  };

  const rulesTab = async (box) => {
    const data = await api('GET', '/detections/rules');
    box.append(table([['Rule', (r) => r.rule_code], ['What it detects', (r) => r.description], ['Enabled', (r) => badge(r.enabled ? 'ENABLED' : 'DISABLED', r.enabled ? 'ok' : 'grey')],
      ['', (r) => isRole('ADMIN') ? h('button', { type: 'button', onclick: guard(async () => { await api('PATCH', `/detections/rules/${r.rule_code}`, { enabled: !r.enabled }); location.reload(); }) },
        r.enabled ? 'Disable' : 'Enable') : '']], data.items));
  };

  root.append(tabs([{ id: 'alerts', label: 'Alerts', render: alertsTab }, { id: 'candidates', label: 'What is missing right now', render: candidatesTab },
    { id: 'rules', label: 'Detection rules', render: rulesTab }]), detail);
}
