import { api, h, money } from '/static/app.js';

const tile = (n, label, href, kind) =>
  h(href ? 'a' : 'div', { class: 'tile', href }, h('div', { class: 'n' + (kind ? ' ' + kind : '') }, n ?? 0), h('div', { class: 'l' }, label));

const sum = (o, ...keys) => keys.reduce((a, k) => a + (o?.[k] || 0), 0);

export default async function (root, { user }) {
  const d = await api('GET', '/reports/dashboard');
  root.append(h('h1', {}, 'Dashboard'), h('p', { class: 'muted' }, `Signed in as ${user.full_name} (${user.role}).`));

  if (d.complaints) {                                   // municipal staff and auditors
    root.append(h('h2', {}, 'Complaints and work'),
      h('div', { class: 'grid' },
        tile(d.complaints.OPEN, 'Open complaints', '/app/complaints'),
        tile(d.complaints.IN_PROGRESS, 'In progress', '/app/complaints'),
        tile(d.complaints.RESOLVED, 'Resolved', '/app/complaints'),
        tile(sum(d.contractors, 'SUSPENDED', 'BLACKLISTED'), 'Contractor status records marked restricted (internal status)', '/app/registry#contractors')),
      h('h2', {}, 'Entry permits'),
      h('div', { class: 'grid' },
        tile(d.permits.DRAFT, 'Drafts awaiting the gate', '/app/permits'),
        tile(d.permits.AUTHORISED, 'Permits with recorded AUTHORISED status (check current policy and receipt)', '/app/permits'),
        tile(d.permits.CLOSED, 'Closed', '/app/permits'),
        tile(sum(d.permits, 'ABORTED', 'CANCELLED'), 'Aborted or cancelled', '/app/permits')));
    if (d.draft_permits_not_ready !== undefined) {
      root.append(h('div', { class: 'grid' }, tile(d.draft_permits_not_ready, 'Draft permits that would be DENIED right now', '/app/permits')));
    }
  }
  if (d.alerts) {
    const overdue = d.compensation_overdue || { cases: 0, outstanding: 0 };
    root.append(h('h2', {}, 'Shadow entries (detected by absence)'),
      h('div', { class: 'grid' },
        tile(d.alerts.OPEN, 'Open alerts', '/app/shadow'),
        tile(d.alerts.EVIDENCE_RECEIVED, 'Late evidence: needs a human decision', '/app/shadow'),
        tile(d.alerts.CONFIRMED, 'Alerts reviewed as likely shadow-entry', '/app/shadow'),
        tile(d.invoices_on_hold, 'Invoices on hold', '/app/invoices')),
      h('h2', {}, 'Consequences and policy'),
      h('div', { class: 'grid' },
        tile(overdue.cases, 'Overdue compensation cases', '/app/incidents#overdue'),
        tile(money(overdue.outstanding), 'Compensation outstanding (overdue)', '/app/incidents#overdue'),
        tile(d.zero_entry_rate_pct === null ? '–' : d.zero_entry_rate_pct + ' %', 'Zero-entry rate (jobs kept mechanised)', '/app/reports')));
  }
  if (d.jobs !== undefined) {                           // contractor
    root.append(h('h2', {}, 'Your work'),
      h('div', { class: 'grid' },
        tile(d.jobs, 'Jobs', '/app/permits'),
        tile(sum(d.permits, 'DRAFT', 'AUTHORISED'), 'Permits in progress', '/app/permits'),
        tile(d.invoices_on_hold, 'Invoices on hold', '/app/invoices'),
        tile(d.incidents, 'Incidents on your record', '/app/incidents')));
  }
  if (d.my_permits) {                                   // worker
    root.append(h('h2', {}, 'Your permits'),
      h('div', { class: 'grid' },
        tile(d.my_permits.AUTHORISED, 'Permits with recorded decision status (check current policy and receipt)', '/app/permits'),
        tile(d.my_permits.DRAFT, 'Being prepared', '/app/permits'),
        tile(sum(d.my_permits, 'CLOSED', 'ABORTED', 'CANCELLED'), 'Finished', '/app/permits')),
      h('p', { class: 'muted' }, 'You can refuse an entry at any time with “Stop work” on the permit page. No one can overrule that in this system.'));
  }
}
