import { api, h, money } from '/static/app.js';

const sum = (o, ...keys) => keys.reduce((a, k) => a + (o?.[k] || 0), 0);

const attention = (value, label, detail, href, classes = '') => {
  const quiet = Number(value ?? 0) === 0 ? ' quiet' : '';
  return h('a', { class: `attention-item ${classes}${quiet}`.trim(), href },
    h('div', { class: 'attention-number' }, value ?? 0),
    h('div', {}, h('div', { class: 'attention-label' }, label), h('div', { class: 'attention-detail' }, detail)));
};

const metric = (value, label, href) =>
  h('a', { class: 'metric-row', href }, h('span', { class: 'metric-label' }, label), h('strong', { class: 'metric-value' }, value ?? 0));

const metricGroup = (title, items) =>
  h('section', { class: 'metric-group' }, h('h2', {}, title), h('div', { class: 'metric-list' }, items));

export default async function (root, { user }) {
  const d = await api('GET', '/reports/dashboard');
  root.append(h('header', { class: 'page-intro' },
    h('p', { class: 'eyebrow' }, 'Default-deny operations'),
    h('h1', {}, 'Entry safety overview'),
    h('p', { class: 'muted' }, `${user.full_name} · ${user.role}. Recorded evidence determines every permit decision.`)));

  if (d.complaints) {
    if (d.alerts) {
      const overdue = d.compensation_overdue || { cases: 0, outstanding: 0 };
      root.append(h('section', {}, h('h2', {}, 'Needs attention'),
        h('div', { class: 'attention-board' },
          attention(d.alerts.OPEN, 'Open shadow-entry alerts', 'Clearance evidence is absent and needs review.', '/app/shadow', 'primary danger'),
          attention(d.alerts.EVIDENCE_RECEIVED, 'Late evidence awaiting a decision', 'Evidence never closes an alert automatically.', '/app/shadow'),
          attention(d.draft_permits_not_ready ?? 0, 'Draft permits denied by current checks', 'Open a draft to see each failing clause.', '/app/permits'),
          attention(d.invoices_on_hold, 'Invoices currently held', 'Alert or incident provenance controls release.', '/app/invoices'),
          attention(overdue.cases, 'Overdue compensation cases', `${money(overdue.outstanding)} remains outstanding.`, '/app/incidents#overdue', 'danger'))));
    }

    root.append(
      metricGroup('Complaint workflow', [
        metric(d.complaints.OPEN, 'Open complaints', '/app/complaints'),
        metric(d.complaints.IN_PROGRESS, 'Work in progress', '/app/complaints'),
        metric(d.complaints.RESOLVED, 'Resolved complaints', '/app/complaints'),
        metric(sum(d.contractors, 'SUSPENDED', 'BLACKLISTED'), 'Restricted contractors', '/app/registry#contractors'),
      ]),
      metricGroup('Permit record', [
        metric(d.permits.DRAFT, 'Drafts awaiting the gate', '/app/permits'),
        metric(d.permits.AUTHORISED, 'Authorised for entry', '/app/permits'),
        metric(d.permits.CLOSED, 'Closed permits', '/app/permits'),
        metric(sum(d.permits, 'ABORTED', 'CANCELLED'), 'Aborted or cancelled', '/app/permits'),
      ]));

    if (d.alerts) {
      root.append(metricGroup('Measured outcomes', [
        metric(d.alerts.CONFIRMED, 'Confirmed shadow entries', '/app/shadow'),
        metric(d.zero_entry_rate_pct === null ? '–' : d.zero_entry_rate_pct + ' %', 'Jobs kept mechanised', '/app/reports'),
      ]));
    }
  }

  if (d.jobs !== undefined) {
    root.append(metricGroup('Your work', [
      metric(d.jobs, 'Jobs', '/app/permits'),
      metric(sum(d.permits, 'DRAFT', 'AUTHORISED'), 'Permits in progress', '/app/permits'),
      metric(d.invoices_on_hold, 'Invoices on hold', '/app/invoices'),
      metric(d.incidents, 'Incidents on record', '/app/incidents'),
    ]));
  }

  if (d.my_permits) {
    root.append(metricGroup('Your permits', [
      metric(d.my_permits.AUTHORISED, 'Authorised permits', '/app/permits'),
      metric(d.my_permits.DRAFT, 'Permits being prepared', '/app/permits'),
      metric(sum(d.my_permits, 'CLOSED', 'ABORTED', 'CANCELLED'), 'Finished permits', '/app/permits'),
    ]), h('p', { class: 'banner warn' }, 'You can refuse entry at any time with “Stop work” on the permit page. No one can overrule that decision in this system.'));
  }
}
