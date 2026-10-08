import { api, badge, fmtDT, form, h, isRole, options, refreshPage, state, table, toast } from '/static/app.js';

const ALLOWED_REPORTERS = ['ADMIN', 'ENGINEER', 'SUPERVISOR'];

export default async function (root) {
  const role = state.user?.role;
  let selectedScope = state.user?.ulb_id;
  root.append(h('h1', {}, 'Incident reports'),
    h('p', { class: 'muted' }, 'Standalone reports can be recorded without a permit, registered worker, contractor, or municipal job. A missing link stays unknown; do not create a person or work order to fill the gap.'),
    h('p', { class: 'banner warn' }, 'Cases begin as pending reference reviews. A reference amount is not an award or payment. Missing documentation supports human review; it does not prove an unlawful entry.'),
    h('h2', {}, 'Recent reports'));

  const list = h('div', { role: 'status', 'aria-live': 'polite' }, h('p', { class: 'muted' }, 'Loading reports…'));
  root.append(list);
  if (role === 'AUDITOR') {
    try {
      const ulbs = await options('/ulbs?limit=200', (u) => [u.ulb_id, u.name]);
      root.insertBefore(h('div', { class: 'panel' }, form([{ name: 'ulb_id', label: 'Municipal scope', type: 'select', required: true, int: true,
        value: selectedScope, options: ulbs }], async (v) => { selectedScope = v.ulb_id; await refreshList(); }, { submit: 'Load reports in this scope' })), list);
    } catch (error) { list.replaceChildren(h('p', { class: 'banner bad' }, `Municipal scope lookup failed: ${error.message}.`)); }
  }
  await refreshList();

  const detail = h('div', { 'aria-live': 'polite' });
  root.append(detail);
  async function openReport(id) {
    detail.replaceChildren(h('p', { class: 'muted' }, 'Loading report from the server…'));
    try {
      const report = await api('GET', `/incident-reports/${id}`);
      detail.replaceChildren(h('section', { class: 'panel' }, h('div', { class: 'row between' },
        h('h2', {}, `Report #${report.report_id}`), h('button', { type: 'button', onclick: () => detail.replaceChildren() }, 'Close details')),
      h('p', { class: 'banner warn' }, `${report.classification_status || 'REVIEW_REQUIRED'} · external award/payment status is not supplied by this report view`),
      h('dl', { class: 'grid' }, ...[
        ['Site', report.site_label], ['Occurred', fmtDT(report.occurred_at)], ['Hazard', report.hazard_type], ['Description', report.description],
        ['Job reference', report.job_id || 'not linked'], ['Permit reference', report.permit_id || 'not linked'], ['Contractor reference', report.contractor_id || 'not linked'],
        ['Reported sections', report.reported_sections || 'not supplied'],
      ].map(([label, value]) => h('div', { class: 'tile' }, h('dt', { class: 'l' }, label), h('dd', {}, value || 'unknown')))),
      h('h3', {}, 'Victim aliases and outcomes'), table([['Alias', (v) => v.display_alias || 'not supplied'], ['Outcome', (v) => badge(v.outcome || 'UNKNOWN', 'warn')],
        ['Registry reference', (v) => v.worker_id || 'none confirmed'], ['Case status', (v) => v.case?.status || 'not supplied'],
        ['Reference amount', (v) => v.case?.reference_amount ? `${v.case.reference_amount} (not an award)` : 'not supplied'],
        ['Recorded paid amount', (v) => v.case?.paid_amount ?? 'not supplied']], report.victims || [], 'No victim records returned.'),
      h('p', { class: 'small muted' }, 'No entry, permit, contractor, payment, or legal conclusion is inferred from an absent record.')));
    } catch (error) {
      detail.replaceChildren(h('p', { class: 'banner bad', role: 'alert' }, `Could not load report #${id}: ${error.message}`));
    }
  }

  if (!ALLOWED_REPORTERS.includes(role)) {
    root.append(h('h2', {}, 'New report'), h('p', { class: 'muted' }, 'Your role can review reports but cannot create one.'));
    return;
  }

  const victimRows = [];
  const victimBox = h('div', { class: 'grid', 'aria-label': 'Victim entries' });
  const addVictim = () => {
    const alias = h('input', { type: 'text', required: true, maxlength: '120', autocomplete: 'off', 'aria-label': 'Victim alias' });
    const outcome = h('select', { required: true, 'aria-label': 'Outcome' },
      h('option', { value: '' }, 'Choose an outcome'),
      ...[['FATAL', 'Fatality reported'], ['INJURY', 'Injury reported'], ['OTHER', 'Other / uncertain']].map(([value, label]) => h('option', { value }, label)));
    const workerId = h('input', { type: 'number', min: '1', step: '1', 'aria-label': 'Confirmed worker registry ID, optional' });
    const row = h('fieldset', { class: 'panel' }, h('legend', {}, `Victim ${victimRows.length + 1}`),
      h('label', {}, 'Alias used in this report', alias), h('label', {}, 'Reported outcome', outcome),
      h('label', {}, 'Confirmed registry ID (optional)', workerId), h('p', { class: 'small muted' }, 'Leave the registry ID blank when identity is unknown or not matched.'),
      h('button', { type: 'button', class: 'danger', onclick: () => {
        if (victimRows.length <= 1) { toast('Keep at least one victim entry.', 'bad'); return; }
        const index = victimRows.findIndex((v) => v.row === row);
        if (index >= 0) victimRows.splice(index, 1);
        row.remove();
      } }, 'Remove victim'));
    victimRows.push({ row, alias, outcome, workerId, victimKey: crypto.randomUUID() });
    victimBox.append(row);
  };
  addVictim();

  const scopeFields = isRole('ADMIN') ? [{ name: 'ulb_id', label: 'Municipal scope', type: 'select', required: true, int: true,
    options: await options('/ulbs?limit=200', (u) => [u.ulb_id, u.name]) }] : [];
  const reportForm = form([
    ...scopeFields,
    { name: 'occurred_at', label: 'Occurred (India time)', type: 'datetime', required: true, value: 'now' },
    { name: 'site_label', label: 'Site or location description', required: true, max: 240 },
    { name: 'hazard_type', label: 'Reported hazard', required: true, max: 120 },
    { name: 'job_id', label: 'Known job ID (optional)', type: 'number', int: true, min: 1 },
    { name: 'permit_id', label: 'Known permit ID (optional)', type: 'number', int: true, min: 1 },
    { name: 'contractor_id', label: 'Confirmed contractor ID (optional)', type: 'number', int: true, min: 1 },
    { name: 'reported_sections', label: 'Reported case or FIR sections (optional)', max: 500 },
    { name: 'description', label: 'What was reported', type: 'textarea', required: true, wide: true },
  ], async (values) => {
    const victims = victimRows.map(({ alias, outcome, workerId, victimKey }) => ({
      victim_key: victimKey, display_alias: alias.value.trim(), outcome: outcome.value,
      ...(workerId.value ? { worker_id: Number(workerId.value) } : {}),
    }));
    if (victims.some((v) => !v.display_alias || !v.outcome)) throw new Error('Each victim needs an alias and an outcome.');
    const scopeId = values.ulb_id ?? state.user?.ulb_id;
    if (!scopeId) throw new Error('Your account has no municipal scope. The server cannot accept this report until a scope is selected.');
    const body = { ...values, ulb_id: Number(scopeId), victims };
    if (body.reported_sections) { body.reported_sections = body.reported_sections.trim(); }
    const result = await api('POST', '/incident-reports', body);
    toast(`Report #${result.report_id} recorded. Payment status: ${result.payment_status || 'NOT_PAID'}.`, 'ok');
    await refreshList();
    await refreshPage();
  }, { submit: 'Record pending report', danger: true });
  const victimsSection = h('section', { class: 'wide' }, h('h3', {}, 'Victims (add each person separately)'),
    h('p', { class: 'small muted' }, 'Aliases are sufficient. Do not invent registry IDs or personal details.'), victimBox,
    h('button', { type: 'button', onclick: addVictim }, 'Add another victim'));
  reportForm.insertBefore(victimsSection, reportForm.lastElementChild);
  root.append(h('h2', {}, 'New report'), h('div', { class: 'panel' }, reportForm));

  async function refreshList() {
    if (role === 'AUDITOR' && !selectedScope) {
      list.replaceChildren(h('p', { class: 'banner warn' }, 'Choose a municipal scope to load incident reports. No scope is inferred.'));
      return;
    }
    try {
      const scope = selectedScope ? `&ulb_id=${encodeURIComponent(selectedScope)}` : '';
      const response = await api('GET', `/incident-reports?limit=50${scope}`);
      list.replaceChildren(table([
        ['Report', (r) => r.report_id], ['Occurred', (r) => fmtDT(r.occurred_at)], ['Site', (r) => r.site_label || 'not recorded'],
        ['Hazard', (r) => r.hazard_type || 'unknown'], ['Classification', (r) => badge(r.classification_status || 'REVIEW_REQUIRED', 'warn')],
        ['Victims and outcomes', (r) => (r.victims || []).map((v) => `${v.display_alias || 'alias not supplied'} · ${v.outcome || 'unknown'}`).join('; ') || 'not supplied'],
        ['Case/payment status', (r) => (r.victims || []).map((v) => v.case?.status || 'review status not supplied').join('; ') || 'case details not supplied'],
        ['', (r) => h('button', { type: 'button', class: 'link', onclick: () => openReport(r.report_id) }, 'View report')],
      ], response.items || [], 'No incident reports in this scope.'));
    } catch (error) { list.replaceChildren(h('p', { class: 'banner bad' }, `Could not refresh report list: ${error.message}`)); }
  }
}
