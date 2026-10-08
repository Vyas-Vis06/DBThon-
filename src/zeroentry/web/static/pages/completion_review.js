import { api, badge, fmtDT, form, h, isRole, options, state, table, toast } from '/static/app.js';

export default async function (root) {
  root.append(h('h1', {}, 'Completion accountability'),
    h('p', { class: 'muted' }, 'Imported completion claims are compared with job evidence, mechanical outcomes, actual participation, and open-entry state. A mismatch is an evidence gap for review, not proof of an unrecorded entry or misconduct.'),
    h('p', { class: 'banner warn' }, 'Source claims remain separate from certified internal completion. Human review does not rewrite the original claim or create a legal finding.'),
    h('h2', {}, 'Current job reconciliation'));

  const resultBox = h('div', { 'aria-live': 'polite' }, h('p', { class: 'muted' }, 'Loading reconciliation…'));
  root.append(resultBox);
  const needsChosenScope = isRole('ADMIN', 'AUDITOR');
  let ulbOptions = [];
  if (needsChosenScope) {
    try { ulbOptions = await options('/ulbs?limit=200', (u) => [u.ulb_id, u.name]); }
    catch (error) { resultBox.replaceChildren(h('p', { class: 'banner bad' }, `Municipal scopes unavailable: ${error.message}`)); }
    root.insertBefore(h('div', { class: 'panel' }, form([
      { name: 'ulb_id', label: 'Municipal scope', type: 'select', required: true, int: true, value: state.user?.ulb_id, options: ulbOptions },
    ], async (v) => { await load(v.ulb_id); }, { submit: 'Load reconciliation scope' })), resultBox);
  }
  async function load(scopeId = state.user?.ulb_id) {
    if (!scopeId) {
      resultBox.replaceChildren(h('p', { class: 'banner warn' }, 'Choose a municipal scope to load reconciliations. No scope is inferred.'));
      return;
    }
    resultBox.replaceChildren(h('p', { class: 'muted', role: 'status' }, 'Refreshing current server reconciliation…'));
    try {
      const result = await api('GET', `/completion-reconciliation?ulb_id=${encodeURIComponent(scopeId)}&limit=100`);
      resultBox.replaceChildren(h('p', { class: 'small muted' }, `${result.total ?? result.items?.length ?? 0} reconciliation row(s) · computed from current evidence`),
        table([['Claim', (r) => r.claim_id ?? 'not supplied'], ['Source / external ID', (r) => `${r.source || 'unknown'} · ${r.external_id || 'unknown'}`],
          ['External job ref', (r) => r.external_job_ref || 'not supplied'], ['Linked job', (r) => r.matched_job_id ?? 'unmatched'],
          ['Claimed status', (r) => r.claimed_status || 'unknown'], ['Match status', (r) => badge(r.match_status || 'UNKNOWN', 'warn')],
          ['Evidence gap', (r) => r.gap_code || 'No gap code supplied; this is not a verified completion'],
          ['Human review', (r) => reviewControl(r, scopeId)]], result.items || [], 'No reconciliation rows were returned. This does not imply every job is verified.'));
    } catch (error) {
      resultBox.replaceChildren(h('p', { class: 'banner bad', role: 'alert' }, `Reconciliation is unavailable: ${error.message}. No local result or assumed pass is shown.`));
    }
  }
  function reviewControl(row, scopeId) {
    if (!isRole('ADMIN', 'ENGINEER') || !row.claim_id) return 'Review action unavailable to this role.';
    const candidates = row.job_candidates || [];
    return h('details', {}, h('summary', {}, 'Record review'),
      h('p', { class: 'small muted' }, 'This records an explicit reviewer decision only; the external claim remains separate from certified completion.'),
      form([
        { name: 'decision', label: 'Review result', type: 'select', required: true, options: [
          { value: 'AMBIGUOUS', label: 'Ambiguous / keep unmatched' }, { value: 'MATCHED', label: 'Link to selected existing job' },
        ] },
        { name: 'job_id', label: 'Candidate internal job (required for link)', type: 'select', int: true,
          options: candidates.map((job) => ({ value: job.job_id, label: `Job #${job.job_id} · ${job.manhole_code || 'location unknown'} · ${job.description || job.status || 'candidate'}` })) },
        { name: 'reason', label: 'Reviewer rationale', type: 'textarea', required: true, max: 1000 },
      ], async (v) => {
        if (v.decision === 'MATCHED' && !v.job_id) throw new Error('Choose an existing candidate job before recording a match.');
        if ((v.reason || '').trim().length < 20) throw new Error('Reviewer rationale must be at least 20 characters.');
        const body = { decision: v.decision, reason: v.reason, ...(v.decision === 'MATCHED' ? { job_id: v.job_id } : {}) };
        await api('POST', `/completion-claims/${row.claim_id}/match`, body);
        toast(`Reviewer decision recorded for claim #${row.claim_id}. The source claim remains unchanged.`);
        await load(scopeId);
      }, { submit: 'Save explicit review' }));
  }
  if (state.user?.ulb_id) await load(state.user.ulb_id);
  else if (!needsChosenScope) await load();

  if (isRole('ADMIN', 'ENGINEER')) {
    root.append(h('h2', {}, 'Import an external completion claim'),
      h('p', { class: 'small muted' }, 'The authenticated server supplies the source scope. Use the source’s stable claim ID and preserve the status as reported.'),
      h('div', { class: 'panel' }, form([
        ...(isRole('ADMIN') ? [{ name: 'ulb_id', label: 'Municipal source scope', type: 'select', required: true, int: true,
          options: ulbOptions }] : []),
        { name: 'source', label: 'Source system', required: true, max: 100 },
        { name: 'external_id', label: 'External claim ID', required: true, max: 160 },
        { name: 'external_job_ref', label: 'External job reference (optional)', max: 160 },
        { name: 'claimed_status', label: 'Claimed status', required: true, max: 80 },
        { name: 'claimed_at', label: 'Claimed completion time (India time)', type: 'datetime', required: true },
        { name: 'source_note', label: 'Source note (optional)', type: 'textarea', wide: true, max: 2000 },
      ], async (values) => {
        const { source_note, ...body } = values;
        body.payload = source_note ? { source_note } : {};
        const response = await api('POST', '/completion-claims', body);
        const projection = response.projection || {};
        toast(`Claim #${response.claim_id} recorded (${response.match_status || 'match status unknown'}).`, 'ok');
        const prior = document.getElementById('claim-result');
        const detail = h('section', { id: 'claim-result', class: 'panel', role: 'status' },
          h('h3', {}, 'Claim received'),
          h('p', { class: 'banner warn' }, `Match state: ${response.match_status || 'unknown'}. A claim is not internal completion.`),
          h('p', {}, `Matched job: ${response.matched_job_id ?? 'none confirmed'}`),
          h('p', {}, `Evidence gap: ${projection.has_gap === true ? 'review required' : projection.has_gap === false ? 'none reported' : 'unknown'}`),
          h('p', { class: 'small muted' }, (projection.gap_codes || []).join(', ') || 'No detailed reason supplied.'));
        if (prior) prior.replaceWith(detail); else root.append(detail);
        await load(values.ulb_id ?? state.user?.ulb_id);
      }, { submit: 'Record external claim' })));
  }

  root.append(h('h2', {}, 'Interpretation'), h('ul', {},
    h('li', {}, 'A claim with no matching job remains unmatched; the system does not invent one.'),
    h('li', {}, 'A matching job with absent or inconsistent evidence is shown for human review.'),
    h('li', {}, 'A valid historical completion is not made invalid just because evidence naturally ages later.'),
    h('li', {}, 'No invoice or legal sanction is inferred unless the server reports its source and state.')));
}
