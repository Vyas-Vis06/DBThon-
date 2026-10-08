import { api, badge, fmtDT, h, kv, money, table, tabs } from '/static/app.js';

const bar = (pct) => h('div', { class: 'bar', role: 'img', 'aria-label': pct + ' percent' }, h('span', { style: undefined, 'data-w': pct }));
// CSP forbids inline style attributes, so bar widths are set through the CSSOM after insertion.
const sizeBars = (root) => root.querySelectorAll('.bar > span[data-w]').forEach((s) => { s.style.width = Math.max(0, Math.min(100, Number(s.dataset.w))) + '%'; });

export default async function (root) {
  root.append(h('h1', {}, 'Reports'), h('p', { class: 'muted' }, 'Each report is a database view or aggregate query; the object behind it is named under the table. Payment values shown here are recorded fields, not external disbursement proof.'),
    h('p', { class: 'banner warn' }, 'These aggregates describe this system’s records and configured scope. They do not measure deaths prevented or prove a legal outcome.'));

  const zeroEntry = async (box) => {
    const data = await api('GET', '/reports/ulb-kpis');
    box.append(h('p', { class: 'muted' }, 'Recorded mechanised-job share for the selected system data. It is not an impact measure. View: v_ulb_year_kpi.'),
      table([['Zone', (r) => r.ulb_name], ['Year', (r) => r.year], ['Jobs', (r) => r.jobs], ['Mechanised', (r) => r.mechanised_jobs], ['Manual exceptions', (r) => r.manual_exception_jobs],
        ['Zero-entry rate', (r) => h('div', { class: 'row' }, bar(Number(r.zero_entry_rate_pct)), Number(r.zero_entry_rate_pct) + ' %')]], data.zero_entry, 'No jobs yet.'),
      h('h2', {}, 'Incidents and deaths per zone per year'), h('p', { class: 'muted' }, 'View: v_ulb_year_incidents (COUNT, SUM, AVG).'),
      table([['Zone', (r) => r.ulb_name], ['Year', (r) => r.year], ['Incidents', (r) => r.incidents], ['Deaths', (r) => r.deaths], ['Compensation due', (r) => money(r.compensation_due)],
        ['Paid', (r) => money(r.compensation_paid)], ['Mean days to compensation', (r) => r.mean_days_to_compensation ?? 'not yet paid']], data.incidents, 'No incidents recorded.'));
    sizeBars(box);
  };

  const risk = async (box) => {
    const data = await api('GET', '/reports/contractor-risk');
    box.append(h('p', { class: 'muted' }, 'Illustrative internal review index: 10 × recorded deaths + 5 × disabilities + 3 × alerts reviewed as likely + 1 × open alerts + 2 × overdue case records. It is not a legal finding or culpability score. View: v_contractor_risk.'),
      table([['Contractor', (r) => r.name], ['Status', (r) => badge(r.status)], ['Deaths', (r) => r.fatalities], ['Disabilities', (r) => r.disabilities],
        ['Confirmed alerts', (r) => r.confirmed_alerts], ['Open alerts', (r) => r.open_alerts], ['Overdue cases', (r) => r.overdue_cases], ['Risk score', (r) => h('strong', {}, r.risk_score)]], data.items));
  };

  const money_ = async (box) => {
    const [overdue, summary] = await Promise.all([api('GET', '/reports/compensation-overdue'), api('GET', '/reports/summary')]);
    const c = summary.complaints, m = summary.compensation;
    box.append(h('h2', {}, 'Overdue compensation'), h('p', { class: 'muted' }, 'View: v_compensation_overdue.'),
      table([['Case', (r) => r.case_id], ['Contractor', (r) => r.contractor_name], ['Type', (r) => badge(r.incident_type)], ['Outstanding', (r) => money(r.amount_outstanding)],
        ['Was due', (r) => r.due_by], ['Days overdue', (r) => h('strong', {}, r.days_overdue)]], overdue.items, 'Nothing overdue.'),
      h('h2', {}, 'Aggregates (COUNT, SUM, AVG, MIN, MAX)'),
      kv([['Complaints', c.complaints], ['Resolved', c.resolved], ['Average hours to resolve', c.avg_hours_to_resolve ?? '–'], ['Fastest (h)', c.min_hours_to_resolve ?? '–'], ['Slowest (h)', c.max_hours_to_resolve ?? '–'],
        ['Compensation cases', m.cases], ['Total due', money(m.total_due)], ['Total paid', money(m.total_paid)], ['Average case', money(m.avg_case)],
        ['Earliest deadline', m.earliest_deadline ?? '–'], ['Latest deadline', m.latest_deadline ?? '–']]));
  };

  const shadow = async (box) => {
    const [summary, ready] = await Promise.all([api('GET', '/reports/shadow-summary'), api('GET', '/reports/permit-readiness')]);
    box.append(h('h2', {}, 'Shadow-entry alerts by rule and status'), h('p', { class: 'muted' }, 'GROUP BY with COUNT and MIN over shadow_entry_alert.'),
      table([['Rule', (r) => r.rule_code], ['Status', (r) => badge(r.status)], ['Alerts', (r) => r.alerts], ['Oldest detected', (r) => fmtDT(r.oldest)]], summary.items, 'No alerts yet.'),
      h('h2', {}, 'Draft permits and what they are missing right now'), h('p', { class: 'muted' }, 'View: v_permit_compliance, which evaluates the legal-clause gate for every draft.'),
      table([['Permit', (r) => h('a', { href: '/app/permit?id=' + r.permit_id }, '#' + r.permit_id)], ['Clauses failing', (r) => `${r.clauses_failed} of ${r.clauses_total}`],
        ['Current configured preview', (r) => r.ready_to_authorise ? badge('CHECKS PASS · NOT A RECEIPT', 'info') : badge('INCOMPLETE', 'warn')], ['Failing', (r) => r.failing_clauses || '']], ready.items, 'No draft permits.'));
  };

  root.append(tabs([{ id: 'zero', label: 'Zero-entry and incidents', render: zeroEntry }, { id: 'risk', label: 'Contractor risk', render: risk },
    { id: 'money', label: 'Compensation and totals', render: money_ }, { id: 'shadow', label: 'Shadow entries and readiness', render: shadow }]));
}
