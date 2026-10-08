import { ago, api, badge, clauseList, fmtDT, form, h, isRole, kv, localIST, nowLocalIST, options, pager, refreshPage, state, table, tabs, toast, toIso } from '/static/app.js';

const BANNER = {
  AUTHORISED: ['ok', 'ENTRY AUTHORISED'], CLOSED: ['warn', 'PERMIT CLOSED'], ABORTED: ['bad', 'PERMIT ABORTED (stop-work)'], CANCELLED: ['warn', 'PERMIT CANCELLED'],
};

export default async function (root, { params }) {
  const id = params.get('id');
  const d = await api('GET', `/permits/${id}`);
  const p = d.permit;
  const policyMode = d.policy_mode || d.policy?.policy_mode || p.policy_mode || state.user?.policy_mode;
  const educational = d.educational === true || d.policy?.educational === true || p.educational === true || state.user?.educational === true || policyMode === 'EDUCATIONAL';
  const supervisor = isRole('SUPERVISOR');
  const decide = isRole('SUPERVISOR', 'ENGINEER');
  const staff = isRole('ADMIN', 'ENGINEER', 'SUPERVISOR', 'AUDITOR');
  const draft = p.status === 'DRAFT';
  const authorised = p.status === 'AUTHORISED';
  const currentDecisionUsable = d.current_decision_usable === true || p.current_decision_usable === true;
  const currentReceiptId = d.current_receipt?.receipt_id ?? d.current_receipt?.id ?? p.latest_certificate_id;
  const canRecordExit = authorised || p.status === 'ABORTED';
  const reload = () => location.reload();

  root.append(
    h('div', { class: 'row between' }, h('h1', {}, `Entry permit #${p.permit_id} `, badge(p.status)), h('a', { href: '/app/permits' }, '← All permits')),
    kv([['Manhole', `${d.complaint.manhole_code} (${d.complaint.manhole_kind}, ${d.complaint.depth_m} m)`], ['Zone', d.complaint.ulb_name],
      ['Contractor', d.job.contractor_name || '–'], ['Complaint', h('a', { href: '/app/complaint?id=' + d.complaint.complaint_id }, '#' + d.complaint.complaint_id)],
      ['Mechanisation waiver', d.waiver ? d.waiver.reason_code.replaceAll('_', ' ') : 'none'], ['Created', fmtDT(p.created_at)],
      p.authorised_at && ['Authorised', fmtDT(p.authorised_at)], p.valid_until && ['Valid until', fmtDT(p.valid_until)],
      p.ended_at && ['Ended', fmtDT(p.ended_at)], p.end_reason && ['Reason', p.end_reason]]));

  const policyText = educational
    ? 'EDUCATIONAL SIMULATION — NOT DEPLOYABLE. A positive decision is only a software demonstration; it does not certify physical conditions or legal permission.'
    : policyMode === 'DENIED'
      ? 'REAL POLICY: DENIED. A waiver or complete evidence cannot override this scope policy.'
      : policyMode === 'REVIEW_REQUIRED'
        ? 'REAL POLICY: REVIEW REQUIRED. Applicability is unresolved; this evidence gap requires qualified human review.'
        : 'POLICY STATUS UNKNOWN. Scope or policy data is missing; treat the status as review required.';
  root.append(h('section', { class: 'panel', 'aria-label': 'Permit policy status' },
    h('p', { class: `banner ${educational ? 'neutral' : policyMode === 'DENIED' ? 'bad' : 'warn'}`, role: 'status' }, policyText),
    h('p', { class: 'small muted' }, 'Policy mode: ', policyMode || 'UNKNOWN', ' · Provenance: ', d.policy_provenance || d.policy?.policy_provenance || d.policy_source || p.policy_source || 'not supplied by the server')));

  // ---- the decision -------------------------------------------------------------------------------------------------
  const decision = h('div', { class: 'panel' });
  root.append(h('h2', {}, 'Entry decision'), decision);

  const showChecklist = (clauses, verdict) => {
    const failing = clauses.filter((c) => !c.passed);
    decision.replaceChildren(
      verdict || h('p', { class: 'banner ' + (failing.length ? 'bad' : 'ok') },
        failing.length ? `INCOMPLETE: ${failing.length} of ${clauses.length} configured checks fail right now.` : `CURRENT PREVIEW: all ${clauses.length} configured checks pass. This is not a committed receipt or permission to enter.`),
      clauseList(clauses), decisionButtons());
  };

  function decisionButtons() {
    if (!draft || !decide) return h('p', { class: 'small muted' }, draft ? 'Only a supervisor or engineer can ask for authorisation.' : '');
    return h('div', { class: 'row' },
      h('button', { type: 'button', onclick: recheck }, 'Re-check the clauses'),
      h('button', { type: 'button', class: 'primary', onclick: authorise }, 'Ask the database to authorise entry'),
      h('span', { class: 'small muted' }, 'Gas readings have a configured freshness limit; re-check before asking.'));
  }

  async function recheck() {
    try { const r = await api('GET', `/permits/${id}/clauses`); showChecklist(r.clauses); toast(r.ready_to_authorise ? 'Every clause passes.' : 'Some clauses still fail.', r.ready_to_authorise ? 'ok' : 'bad'); }
    catch (e) { toast(e.message, 'bad'); }
  }

  async function authorise() {
    try {
      const r = await api('POST', `/permits/${id}/authorise`);
      if (r.authorised) {
        showChecklist(r.clauses, h('p', { class: 'banner neutral' }, 'EDUCATIONAL SIMULATION DECISION RECORDED. The database returned a receipt for this labelled fixture; this is not permission for real-world entry.'));
        setTimeout(() => refreshPage(), 700);
      } else {
        const failed = r.failures?.map((f) => f.code || f.gate || 'UNKNOWN') || r.clauses?.filter((c) => !c.passed).map((c) => c.code || c.clause_code || c.title) || r.failed || [];
        showChecklist(r.clauses || [], h('p', { class: 'banner bad' }, `DENIED${r.receipt_id ? ` · receipt #${r.receipt_id} saved` : ''}: ${failed.length ? failed.join(', ') : 'the server did not return failure detail; refresh the dossier for the committed decision.'}`));
        setTimeout(() => refreshPage(), 700);
      }
    } catch (e) { toast(e.message, 'bad'); }
  }

  if (draft && d.clauses) showChecklist(d.clauses);
  else {
    const [kind, text] = BANNER[p.status] || ['warn', p.status];
    const currentUsable = d.current_decision_usable ?? p.current_decision_usable;
    const statusText = p.status === 'AUTHORISED'
      ? (educational ? `EDUCATIONAL RECEIPT RECORDED: expires ${fmtDT(d.current_receipt?.expires_at || p.valid_until)}.` : 'HISTORICAL AUTHORISED STATE SHOWN. Current scope is not educational; this screen does not grant permission to enter.')
      : text;
    decision.replaceChildren(...[h('p', { class: 'banner ' + (p.status === 'AUTHORISED' && !educational ? 'bad' : kind) }, statusText),
      p.status === 'AUTHORISED' && currentUsable === false && h('p', { class: 'banner bad' }, 'CURRENT DECISION EXPIRED OR STALE. Refresh current evidence and obtain a new server decision; this saved receipt cannot be reused.'),
      p.end_reason && h('p', {}, 'Reason recorded: ', h('em', {}, p.end_reason))].filter(Boolean));   // replaceChildren(null) would print "null"
  }

  // ---- crew, gear, readings, entries, ending -------------------------------------------------------------------------
  const entrants = d.crew.filter((w) => w.crew_role === 'ENTRANT');
  const today = new Date().toISOString().slice(0, 10);
  const fit = (date) => date >= today ? fmtDate10(date) : h('span', { class: 'badge bad' }, 'expired ' + fmtDate10(date));

  const crewTab = async (box) => {
    box.append(table([
      ['Name', (w) => w.full_name], ['Registry reference', (w) => w.namaste_id || 'not recorded'], ['Role', (w) => badge(w.crew_role, w.crew_role === 'ENTRANT' ? 'info' : 'grey')],
      ['Personal acknowledgement', (w) => w.acknowledged_at ? `Acknowledged ${fmtDT(w.acknowledged_at)}` : badge('NOT ACKNOWLEDGED', 'warn')],
      ['Medically fit until', (w) => fit(w.medical_fit_until)], ['Trained until', (w) => fit(w.trained_until)],
      ['', (w) => (draft && supervisor) ? h('button', { type: 'button', class: 'danger', onclick: async () => {
        try { await api('DELETE', `/permits/${id}/crew/${w.worker_id}`); reload(); } catch (e) { toast(e.message, 'bad'); } } }, 'Remove') : ''],
    ], d.crew, 'No crew yet. Unknown or missing assignments are incomplete evidence. A permit needs distinct entrants, a standby and a supervisor.'));
    if (isRole('WORKER') && d.crew.some((w) => Number(w.worker_id) === Number(state.user?.worker_id) && !w.acknowledged_at)) {
      box.append(h('p', { class: 'banner warn' }, 'Your assignment is not personally acknowledged. A supervisor assignment is not your acknowledgement.'),
        h('button', { type: 'button', class: 'primary', onclick: async () => {
          try { await api('POST', `/permits/${id}/acknowledge`, {}); toast('Your acknowledgement was recorded.'); await refreshPage(); }
          catch (e) { toast(e.message, 'bad'); }
        } }, 'Acknowledge my assignment'));
    }
    if (draft && supervisor) {
      const have = new Set(d.crew.map((w) => w.worker_id));
      const workers = (await options(`/workers?contractor_id=${d.job.contractor_id}&limit=200`, (w) => [w.worker_id, `${w.full_name} · ${w.namaste_id}`]))
        .filter((o) => !have.has(o.value));
      box.append(h('h3', {}, 'Add a crew member'), form([
        { name: 'worker_id', label: 'Worker (this contractor)', type: 'select', required: true, int: true, options: workers },
        { name: 'crew_role', label: 'Role on this permit', type: 'select', required: true, options: ['ENTRANT', 'STANDBY', 'SUPERVISOR'].map((r) => ({ value: r, label: r })),
          hint: 'One role per person: a standby can never also be an entrant.' },
      ], async (v) => { await api('POST', `/permits/${id}/crew`, v); reload(); }, { submit: 'Add to crew' }));
    }
  };

  const gearTab = async (box) => {
    const personalRequirements = d.required_personal_gear || d.requirements?.personal || [];
    const siteRequirements = d.required_site_gear || d.requirements?.site || [];
    box.append(h('p', { class: 'muted' }, 'The catalogue is not a universal checklist. The server’s configured personal and shared-site requirements are shown separately; every physical item is identified by its serial asset and availability.'));
    if (personalRequirements.length && entrants.length) {
      box.append(h('h3', {}, 'Personal requirements by entrant'),
        table([['Entrant', (r) => r.worker_name || d.crew.find((w) => Number(w.worker_id) === Number(r.worker_id))?.full_name || `Worker #${r.worker_id}`],
          ['Required item', (r) => r.gear_name || r.gear_code], ['Required', (r) => r.quantity ?? 1], ['Recorded assets', (r) => (r.assets || []).map((a) => `${a.serial_no} (${a.status || 'status unknown'})`).join(', ') || badge('MISSING / UNKNOWN', 'warn')]], personalRequirements,
        'No server-supplied personal requirement mapping. Requirement status is UNKNOWN, not satisfied.'));
    } else {
      box.append(h('p', { class: 'banner warn' }, 'Personal requirement mapping is unavailable from the server. The UI cannot infer what is required from the catalogue.'));
    }
    box.append(h('h3', {}, 'Personal gear issues'), table([
      ['Person', (g) => (d.crew.find((w) => Number(w.worker_id) === Number(g.worker_id)) || {}).full_name || 'Site custody / not linked'],
      ['Item', (g) => g.gear_name || g.gear_code || 'unknown'], ['Serial asset', (g) => g.serial_no || g.asset_serial || 'not supplied'],
      ['Asset status', (g) => badge(g.asset_status || g.status || 'UNKNOWN', g.available === false ? 'bad' : 'grey')],
      ['Evidence source', (g) => g.source_mode || 'not supplied'],
    ], d.gear || [], 'No personal gear issue recorded.'));
    box.append(h('h3', {}, 'Shared site equipment'),
      siteRequirements.length ? table([['Required item', (r) => r.gear_name || r.gear_code], ['Required', (r) => r.quantity ?? 1],
        ['Recorded serial assets', (r) => (r.assets || []).map((a) => `${a.serial_no} (${a.status || 'status unknown'})`).join(', ') || badge('MISSING / UNKNOWN', 'warn')]], siteRequirements,
      'No site requirements were returned.') : h('p', { class: 'banner warn' }, 'Shared-site requirement mapping is unavailable. Do not infer a pass from personal gear.'));
    box.append(table([['Item', (g) => g.gear_code || g.gear_name || 'unknown'], ['Serial asset', (g) => g.serial_no || g.asset_serial || 'not supplied'],
      ['Availability', (g) => badge(g.status || (g.available === true ? 'AVAILABLE' : 'UNKNOWN'), g.available === false ? 'bad' : 'grey')],
      ['Inspection valid through', (g) => g.inspection_validity || 'unknown']], d.site_gear || [], 'No shared-site asset is assigned.'));

    const assetScope = d.policy?.ulb_id || d.complaint?.ulb_id || state.user?.ulb_id;
    if (draft && isRole('ADMIN', 'ENGINEER')) {
      const staffScopeFields = isRole('ADMIN') ? [{ name: 'ulb_id', label: 'Municipal scope', type: 'select', required: true, int: true,
        value: assetScope, options: await options('/ulbs?limit=200', (u) => [u.ulb_id, u.name]) }] : [];
      if (assetScope || isRole('ADMIN')) {
        let catalogue = [];
        let catalogueError = null;
        try { catalogue = await options('/gear-items?limit=200', (g) => [g.gear_code, `${g.name} · ${g.gear_code}`]); }
        catch (error) { catalogueError = error; }
        if (catalogueError) box.append(h('p', { class: 'banner warn' }, `Gear catalogue unavailable: ${catalogueError.message}. No item is inferred.`));
        else if (!catalogue.length) box.append(h('p', { class: 'banner warn' }, 'No gear catalogue items are available to register.'));
        else box.append(h('h3', {}, 'Register an inspected serial asset'), h('p', { class: 'small muted' }, 'Only a real serialized inventory record can be assigned; registration does not itself satisfy a permit requirement.'), form([
          ...staffScopeFields,
          { name: 'gear_code', label: 'Catalogue item', type: 'select', required: true, options: catalogue },
          { name: 'serial_no', label: 'Manufacturer / inventory serial', required: true, max: 60 },
          { name: 'status', label: 'Asset condition', type: 'select', required: true, value: 'USABLE', options: ['USABLE', 'OUT_OF_SERVICE', 'RETIRED'].map((value) => ({ value, label: value.replaceAll('_', ' ') })) },
          { name: 'inspection_valid_until', label: 'Inspection valid through', type: 'date', required: true },
        ], async (v) => {
          const body = { ...v, ulb_id: Number(v.ulb_id ?? assetScope) };
          await api('POST', '/reference/gear-assets', body);
          toast('Serial asset registered. It is not assigned until the separate permit action succeeds.');
          await refreshPage();
        }, { submit: 'Register serial asset' }));
      } else box.append(h('p', { class: 'banner warn' }, 'No municipal scope is attached to this account. Asset registration remains unavailable until the server supplies a scope.'));
    }

    if (draft && supervisor) {
      let assets = [];
      let assetError = null;
      try {
        if (assetScope) assets = (await api('GET', `/reference/gear-assets?ulb_id=${encodeURIComponent(assetScope)}&limit=200`)).items || [];
        else assetError = new Error('The server did not supply a municipal asset scope.');
      }
      catch (error) { assetError = error; }
      const available = assets.filter((asset) => asset.available === true && asset.status === 'USABLE');
      if (assetError) box.append(h('p', { class: 'banner warn', role: 'status' }, `Serial asset inventory unavailable (${assetError.message}). Do not type or invent a serial number; refresh when the inventory service is available.`));
      else if (!available.length) box.append(h('p', { class: 'banner warn' }, 'No available usable serial assets were returned.'));
      else {
        box.append(h('h3', {}, 'Assign a personal asset to a crew member'), form([
          { name: 'worker_id', label: 'Crew member', type: 'select', required: true, int: true, options: d.crew.map((w) => ({ value: w.worker_id, label: `${w.full_name} (${w.crew_role})` })) },
          { name: 'gear_asset_id', label: 'Available serial asset', type: 'select', required: true, int: true, options: available.map((a) => ({ value: a.gear_asset_id, label: `${a.gear_code} · ${a.serial_no} · ${a.status}` })) },
        ], async (v) => {
          const asset = assets.find((item) => Number(item.gear_asset_id) === Number(v.gear_asset_id));
          if (!asset) throw new Error('Selected serial asset is no longer in the loaded inventory. Refresh and choose a current asset.');
          await api('POST', `/permits/${id}/gear`, { ...v, gear_code: asset.gear_code, serial_no: asset.serial_no });
          await refreshPage();
        }, { submit: 'Assign personal asset' }));
        box.append(h('h3', {}, 'Assign a shared-site asset'), form([
          { name: 'gear_asset_id', label: 'Available serial asset', type: 'select', required: true, int: true, options: available.map((a) => ({ value: a.gear_asset_id, label: `${a.gear_code} · ${a.serial_no} · ${a.status}` })) },
        ], async (v) => { await api('POST', `/permits/${id}/site-gear`, v); await refreshPage(); }, { submit: 'Assign site asset' }));
      }
    }
  };

  const gasTab = async (box) => {
    const latestByDepth = new Map();
    for (const reading of [...d.readings].sort((a, b) => new Date(b.taken_at) - new Date(a.taken_at))) {
      if (!latestByDepth.has(reading.depth_level)) latestByDepth.set(reading.depth_level, reading);
    }
    const latestRows = ['TOP', 'MID', 'BOTTOM'].map((depth) => ({ depth, reading: latestByDepth.get(depth) }));
    box.append(h('h3', {}, 'Latest observation by depth'), table([
      ['Depth', (r) => badge(r.depth, 'info')], ['Taken', (r) => r.reading ? fmtDT(r.reading.taken_at) : 'not recorded'],
      ['O₂ %', (r) => r.reading?.o2_pct ?? badge('UNKNOWN', 'warn')], ['H₂S ppm', (r) => r.reading?.h2s_ppm ?? badge('UNKNOWN', 'warn')],
      ['LEL %', (r) => r.reading?.lel_pct ?? badge('UNKNOWN', 'warn')], ['CO ppm', (r) => r.reading?.co_ppm ?? badge('UNKNOWN', 'warn')],
      ['Source', (r) => badge(r.reading?.source_mode || 'UNKNOWN', 'warn')],
    ], latestRows, 'No depth observations returned.'));
    const incompleteDepths = latestRows.filter(({ reading }) => !reading || ['o2_pct', 'h2s_ppm', 'lel_pct', 'co_ppm'].some((key) => reading[key] === null || reading[key] === undefined)).map((r) => r.depth);
    if (incompleteDepths.length) box.append(h('p', { class: 'banner warn', role: 'status' }, `Latest observations are missing one or more channels at ${incompleteDepths.join(', ')}. These remain UNKNOWN and fail completeness; they are not treated as zero.`));
    const gasGate = (d.clauses || []).filter((c) => /GAS|READING/i.test(c.clause_code || ''));
    if (gasGate.length) box.append(h('p', { class: 'small muted' }, 'Current database gate response: ', gasGate.map((c) => `${c.clause_code}: ${c.passed ? 'pass' : 'fail'} — ${c.detail}`).join(' · ')));
    box.append(h('p', { class: 'muted' }, 'For each depth the latest server-selected observation governs, including incomplete or adverse readings. Values shown here are evidence, not proof of physical conditions. A typed or simulated sample is not a certified-instrument measurement; missing channels are UNKNOWN.'),
      table([['Taken (IST)', (r) => [fmtDT(r.taken_at), ' ', h('span', { class: 'small muted' }, ago(r.taken_at))]], ['Depth', (r) => badge(r.depth_level, 'info')],
        ['O₂ %', (r) => r.o2_pct ?? badge('UNKNOWN', 'warn')], ['H₂S ppm', (r) => r.h2s_ppm ?? badge('UNKNOWN', 'warn')], ['LEL %', (r) => r.lel_pct ?? badge('UNKNOWN', 'warn')], ['CO ppm', (r) => r.co_ppm ?? badge('UNKNOWN', 'warn')],
        ['Provenance', (r) => badge(r.source_mode || 'UNKNOWN', 'warn')], ['Quality', (r) => badge(r.quality || 'UNKNOWN', 'warn')], ['Detector', (r) => r.detector_serial || 'unknown'],
        ['Signed off by', (r) => r.recorded_by_name]], d.readings, 'No readings logged yet.'));
    if ((draft || authorised) && decide) {
      const detectors = await options('/detectors?limit=200', (x) => [x.detector_id, `${x.serial_no} · calibrated until ${x.calibration_valid_until}`]);
      const f = form([
        { name: 'detector_id', label: 'Detector', type: 'select', required: true, int: true, options: detectors },
        { name: 'depth_level', label: 'Depth', type: 'select', required: true, options: ['TOP', 'MID', 'BOTTOM'].map((x) => ({ value: x, label: x })) },
        { name: 'source_mode', label: 'How values were obtained', type: 'select', required: true,
          options: [{ value: 'TYPED', label: 'Typed by a person (not certified instrument evidence)' },
            ...(educational ? [{ value: 'SIMULATED', label: 'Simulated fixture values (educational only)' }] : [])] },
        { name: 'o2_pct', label: 'O₂ %', type: 'number', step: '0.1', min: 0, max: 100, hint: 'Leave blank if unknown; blank stays UNKNOWN, never zero.' },
        { name: 'h2s_ppm', label: 'H₂S ppm', type: 'number', step: '0.01', min: 0, hint: 'Leave blank if unknown; blank stays UNKNOWN, never zero.' },
        { name: 'lel_pct', label: 'Combustibles % LEL', type: 'number', step: '0.01', min: 0, max: 100, hint: 'Leave blank if unknown; blank stays UNKNOWN, never zero.' },
        { name: 'co_ppm', label: 'CO ppm', type: 'number', step: '0.01', min: 0, hint: 'Leave blank if unknown; blank stays UNKNOWN, never zero.' },
      ], async (v) => {
        try { await api('POST', `/permits/${id}/readings`, v); reload(); }
        catch (error) { await refreshPage(); throw error; }
      }, { submit: 'Sign off this reading' });
      box.append(h('h3', {}, 'Log an observation (your digital sign-off)'), f);
      if (educational) box.append(h('button', { type: 'button', class: 'link', onclick: () => {
        f.elements.source_mode.value = 'SIMULATED';
        for (const [k, val] of Object.entries({ o2_pct: 20.9, h2s_ppm: 0, lel_pct: 0, co_ppm: 0 })) f.elements[k].value = val;
      } }, 'Fill explicitly simulated fixture values'));
    }
  };

  const readinessTab = async (box) => {
    const rows = d.readiness || d.readiness_evidence || [];
    const kinds = ['STRUCTURE', 'ISOLATION', 'VENTILATION', 'RESCUE', 'COMMUNICATION', 'TRAFFIC', 'MEDICAL'];
    const latest = new Map();
    for (const item of [...rows].sort((a, b) => new Date(b.recorded_at) - new Date(a.recorded_at))) if (!latest.has(item.kind)) latest.set(item.kind, item);
    const readinessSummary = kinds.map((kind) => {
      const item = latest.get(kind);
      const expired = item?.expires_at && new Date(item.expires_at) <= Date.now();
      return { kind, item, state: !item ? 'MISSING' : expired ? 'EXPIRED' : item.passed === true ? 'ATTESTED PASS' : item.passed === false ? 'ADVERSE' : 'UNKNOWN' };
    });
    box.append(h('h3', {}, 'Required readiness by type'), table([
      ['Type', (r) => badge(r.kind, 'info')], ['Current evidence', (r) => badge(r.state, r.state === 'ATTESTED PASS' ? 'ok' : r.state === 'MISSING' || r.state === 'UNKNOWN' ? 'warn' : 'bad')],
      ['Recorded', (r) => fmtDT(r.item?.recorded_at) || 'not recorded'], ['Expires', (r) => fmtDT(r.item?.expires_at) || 'not supplied'],
      ['Source', (r) => r.item?.source_mode || 'UNKNOWN'], ['Details', (r) => Object.entries(r.item?.details || {}).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'not supplied'],
    ], readinessSummary, 'All required readiness types remain unknown without current evidence.'));
    box.append(h('p', { class: 'muted' }, 'These are attributed attestations, not independently verified physical measurements. The latest failing, expired, or missing item remains a reason for review; recording a passing value does not guarantee a decision.'),
      table([['Type', (r) => badge(r.kind || 'UNKNOWN', 'info')], ['Observation', (r) => r.passed === true ? badge('ATTESTED PASS', 'ok') : r.passed === false ? badge('ADVERSE', 'bad') : badge('UNKNOWN', 'warn')],
        ['Recorded', (r) => fmtDT(r.recorded_at)], ['Expires', (r) => fmtDT(r.expires_at) || 'unknown'], ['Attestation details', (r) => Object.entries(r.details || {}).map(([k, v]) => `${k}: ${v}`).join(' · ') || 'not supplied'],
        ['Recorder/source', (r) => r.recorded_by_name || r.source_mode || 'not supplied']], rows, 'No readiness observations. Missing evidence is incomplete, not a pass.'));
    if (draft && supervisor) {
      const detailKeys = {
        STRUCTURE: ['inspection_ref', 'qualified_person_ref'], ISOLATION: ['isolation_ref'],
        VENTILATION: ['opened_at', 'method_ref'], RESCUE: ['plan_ref', 'retrieval_asset_ref'],
        COMMUNICATION: ['method_ref', 'test_ref'], TRAFFIC: ['barrier_ref'], MEDICAL: ['contact_ref', 'first_aid_ref'],
      };
      const labels = {
        inspection_ref: 'Structure inspection reference', qualified_person_ref: 'Qualified person reference',
        isolation_ref: 'Isolation / lockout reference', opened_at: 'Ventilation opened at (India time)', method_ref: 'Method reference',
        plan_ref: 'Rescue plan reference', retrieval_asset_ref: 'Retrieval asset reference', test_ref: 'Test reference',
        barrier_ref: 'Traffic barrier / diversion reference', contact_ref: 'Medical contact reference', first_aid_ref: 'First-aid resource reference',
      };
      const kinds = Object.keys(detailKeys);
      const kind = h('select', { required: true, 'aria-label': 'Readiness type' }, ...kinds.map((value) => h('option', { value }, value)));
      const outcome = h('select', { required: true, 'aria-label': 'Attested outcome' }, h('option', { value: '' }, 'Choose an outcome'),
        h('option', { value: 'true' }, 'Pass observed'), h('option', { value: 'false' }, 'Adverse / failed'));
      const expires = h('input', { type: 'datetime-local', step: '1', required: true, value: nowLocalIST(60), 'aria-label': 'Evidence expires (India time)' });
      const detailsBox = h('fieldset', { class: 'wide' });
      const detailInputs = {};
      for (const [evidenceKind, keys] of Object.entries(detailKeys)) {
        const section = h('fieldset', { class: 'panel', hidden: true, 'data-readiness-kind': evidenceKind }, h('legend', {}, `${evidenceKind} references`));
        for (const key of keys) {
          const isDate = key === 'opened_at';
          const input = h('input', { type: isDate ? 'datetime-local' : 'text', step: isDate ? '1' : undefined,
            value: isDate ? nowLocalIST() : undefined, maxlength: isDate ? undefined : '160', 'aria-label': labels[key] });
          detailInputs[key] = input;
          section.append(h('label', {}, labels[key], input));
        }
        detailsBox.append(section);
      }
      const showKindFields = () => {
        for (const section of detailsBox.children) {
          const active = section.dataset.readinessKind === kind.value;
          section.hidden = !active;
          for (const input of section.querySelectorAll('input')) input.required = active;
        }
      };
      kind.addEventListener('change', showKindFields);
      showKindFields();
      const readinessForm = h('form', { class: 'fields' },
        h('label', {}, 'Readiness type', kind), h('label', {}, 'Attested outcome', outcome),
        h('label', {}, 'Evidence expires (India time)', expires), detailsBox,
        h('p', { class: 'wide small muted' }, 'Only this type’s documented reference fields are sent. These are attributed observations, not independent verification; adverse and incomplete observations remain in the record.'),
        h('div', { class: 'wide' }, h('button', { type: 'submit', class: 'primary' }, 'Record readiness observation')));
      readinessForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (!readinessForm.reportValidity()) return;
        const keys = detailKeys[kind.value] || [];
        const details = Object.fromEntries(keys.map((key) => [key, key === 'opened_at' ? toIso(detailInputs[key].value) : detailInputs[key].value.trim()]));
        const button = readinessForm.querySelector('button[type="submit"]');
        button.disabled = true;
        try {
          await api('POST', `/permits/${id}/readiness`, { kind: kind.value, passed: outcome.value === 'true', expires_at: toIso(expires.value), details });
          toast('Readiness observation recorded. This does not grant entry; request a fresh server decision.');
          await refreshPage();
        } catch (error) { toast(error.message || String(error), 'bad'); }
        finally { button.disabled = false; }
      });
      box.append(h('h3', {}, 'Record an observation'), readinessForm,
        h('p', { class: 'small muted' }, 'A true/false attestation is kept with its source and expiry. No medical details or emergency phone numbers are requested.'));
    }
  };

  const receiptsTab = async (box) => {
    box.append(h('p', { class: 'muted' }, 'Receipts are immutable historical decisions. Current usability is derived from server time, evidence revision, scope policy and permit state. A browser countdown is advisory and never grants permission.'));
    try {
      const response = await api('GET', `/permits/${id}/receipts`);
      const rows = response.items || [];
      const failedChecks = (receipt) => (Array.isArray(receipt.failures) ? receipt.failures : [])
        .filter((failure) => !failure || typeof failure !== 'object' || failure.passed !== true)
        .map((failure) => {
          if (typeof failure === 'string') return failure;
          if (!failure || typeof failure !== 'object') return String(failure ?? 'Failure reason unavailable');
          const code = failure.clause_code || failure.code || failure.gate || failure.kind || 'Unclassified check';
          const detail = failure.detail || failure.message || failure.reason;
          return detail ? `${code}: ${detail}` : code;
        }).filter(Boolean);
      const failuresCell = (receipt) => {
        const failures = failedChecks(receipt);
        if (!failures.length) return 'none recorded';
        const policyFailure = failures.findIndex((failure) => failure.startsWith('POLICY_ELIGIBILITY:'));
        if (policyFailure > 0) failures.unshift(failures.splice(policyFailure, 1)[0]);
        return h('div', {},
          h('p', { class: 'small' }, failures.slice(0, 3).join('; ')),
          failures.length > 3 && h('details', {}, h('summary', {}, `Show ${failures.length - 3} more failed checks`),
            h('ul', {}, failures.slice(3).map((failure) => h('li', {}, failure)))));
      };
      box.append(table([['Receipt', (r) => r.receipt_id ?? 'not supplied'], ['Decision', (r) => badge(r.decision || 'UNKNOWN', r.decision === 'AUTHORISED' ? 'info' : 'bad')],
        ['Evaluated', (r) => fmtDT(r.evaluated_at || r.decision_at)], ['Revision', (r) => r.evidence_revision ?? 'unknown'],
        ['Current usability', (r) => r.usable === true ? badge('USABLE (server-reported)', 'info') : r.usable === false ? badge('EXPIRED / STALE / DENIED', 'bad') : badge('UNKNOWN', 'warn')],
        ['Expires', (r) => fmtDT(r.expires_at) || 'no valid expiry supplied'], ['Failures', failuresCell],
        ['Snapshot digest', (r) => r.snapshot_sha256 || 'not supplied']], rows, 'No committed decision receipts. A preview is not a receipt.'));
    } catch (error) {
      box.append(h('p', { class: 'banner warn', role: 'status' }, `Receipt history unavailable: ${error.message}. The UI cannot infer a current decision.`));
    }
  };

  const entriesTab = async (box) => {
    box.append(h('p', { class: 'muted' }, 'A new entry needs current authorisation, an ENTRANT, a valid permit, and daylight. No worker can have overlapping entries. A 90-minute stretch requires a 30-minute rest; if an exit is reported late, it is still recorded with violation evidence. Open entries remain closable after a permit stop.'),
      table([['Worker', (e) => `${e.worker_name} (${e.namaste_id})`], ['Entered', (e) => fmtDT(e.entered_at)], ['Exited', (e) => e.open ? badge('INSIDE NOW', 'warn') : fmtDT(e.exited_at)],
        ['Minutes', (e) => e.minutes ?? ''],
        ['', (e) => (e.open && supervisor && canRecordExit) ? h('details', {}, h('summary', {}, p.status === 'ABORTED' ? 'Record exit after stop' : 'Record exit'), form([
          { name: 'exited_at', label: 'Exited', type: 'datetime', value: nowLocalIST(1), required: true }],
          async (v) => { await api('POST', `/permits/${id}/entries/${e.entry_id}/exit`, v); reload(); }, { submit: 'Record exit' })) : '']], d.entries, 'No one has entered.'));
    if (authorised && supervisor && educational && currentDecisionUsable && currentReceiptId) {
      box.append(h('h3', {}, 'Record simulated entry'), h('p', { class: 'banner neutral' }, 'This action sends the exact current receipt ID to the server, which rechecks all gates. The browser status and countdown are advisory.'), form([
        { name: 'worker_id', label: 'Acknowledged entrant', type: 'select', required: true, int: true, options: d.crew.filter((w) => w.crew_role === 'ENTRANT' && w.acknowledged_at).map((w) => ({ value: w.worker_id, label: `${w.full_name} (${w.crew_role})` })) },
        { name: 'entered_at', label: 'Entered (India time)', type: 'datetime', required: true,
          value: localIST(new Date(Math.max(Date.now(), new Date(p.authorised_at).getTime() + 1000))), hint: 'Cannot be earlier than the authorisation instant.' },
        { name: 'exited_at', label: 'Exited (leave empty while inside)', type: 'datetime' },
      ], async (v) => {
        try { await api('POST', `/permits/${id}/entries`, { ...v, receipt_id: currentReceiptId }); await refreshPage(); }
        catch (error) { await refreshPage(); throw error; }
      }, { submit: 'Record simulated entry' }));
    } else if (authorised && supervisor) {
      box.append(h('p', { class: 'banner warn', role: 'status' }, !educational
        ? 'No real-world entry action is available from this screen. The current policy is not the educational fixture.'
        : !currentDecisionUsable || !currentReceiptId
          ? 'Current receipt usability or exact receipt ID is unknown, expired, or stale. Refresh the dossier and request a server decision before considering a simulated entry.'
          : 'No acknowledged entrant is available. Missing acknowledgement is incomplete evidence.'));
    }
  };

  const endTab = async (box) => {
    if (!(draft || authorised)) { box.append(h('p', { class: 'muted' }, 'This permit has ended; it is evidence and can no longer change.')); return; }
    const reason = [{ name: 'reason', label: 'Reason (recorded permanently)', type: 'textarea', required: true, wide: true, attrs: { minlength: 5 } }];
    if (authorised && decide) box.append(h('h3', {}, 'Close the permit'), h('p', { class: 'muted' }, 'Everyone must be out first. A closed, authorised permit with logged entries is lawful clearance evidence.'),
      h('button', { type: 'button', class: 'primary', onclick: async () => { try { await api('POST', `/permits/${id}/close`); reload(); } catch (e) { toast(e.message, 'bad'); } } }, 'Close permit'));
    if (decide) {
      box.append(h('h3', {}, authorised ? 'Abort (emergency stop-work)' : 'Cancel this draft'),
        form(reason, async (v) => { await api('POST', `/permits/${id}/${authorised ? 'abort' : 'cancel'}`, v); reload(); }, { submit: authorised ? 'Abort permit' : 'Cancel permit', danger: true }));
    }
    if (isRole('WORKER')) {
      box.append(h('h3', {}, 'Refuse to enter: stop work'), h('p', { class: 'muted' }, 'Any crew member can stop the permit. It cannot be overruled here.'),
        form(reason, async (v) => { await api('POST', `/permits/${id}/stop-work`, v); reload(); }, { submit: 'Stop work', danger: true }));
    } else if (decide && authorised) {
      box.append(h('p', { class: 'small muted' }, 'Crew members can also stop work from their own login.'));
    }
  };

  const originalTab = async (box) => {
    let saved;
    try { saved = await api('GET', `/permits/${id}/decision`); }
    catch (e) {
      if (e.status === 404) { box.append(h('p', { class: 'muted' }, 'An original decision is saved when a new permit is authorised. Older permits may have no saved decision.')); return; }
      throw e;
    }
    const snapshot = saved.snapshot;
    box.append(h('p', { class: 'banner ' + (saved.digest_verified ? 'ok' : 'bad') },
      saved.digest_verified ? 'Saved decision digest verified' : 'Saved decision digest does not match'),
    h('p', {}, `Checks and evidence as recorded at ${fmtDT(saved.decision_at)}. Later policy changes do not rewrite this record.`),
    clauseList(snapshot.gate.map((c) => ({ ...c, legal_ref: c.sources.map((s) => `${s.source_type}: ${s.title} · ${s.citation_clause}`).join('; ') }))),
    h('h3', {}, 'Policy values used'), table([
      ['Parameter', (r) => h('code', {}, r.param_key)], ['Revision', (r) => r.revision], ['Value', (r) => `${r.value} ${r.unit}`],
      ['Basis', (r) => badge(r.source.source_type, r.source.source_type === 'PRODUCT_POLICY' ? 'warn' : 'info')],
      ['Reference', (r) => r.source.source_url ? h('a', { href: r.source.source_url, target: '_blank', rel: 'noopener noreferrer' }, r.source.title) : r.source.title],
    ], snapshot.policy_parameters),
    h('details', {}, h('summary', {}, 'Saved evidence and digest'),
      h('p', { class: 'small muted' }, 'The digest checks the saved content within this database. It is not an external signature or proof that a reported reading was physically true.'),
      h('pre', { class: 'sql' }, saved.snapshot_sha256), h('pre', { class: 'sql' }, JSON.stringify(snapshot.evidence, null, 2))));
  };

  const safetyTab = async (box) => {
    const results = h('div');
    const load = async (offset = 0) => {
      const events = await api('GET', `/permits/${id}/safety-events?limit=25&offset=${offset}`);
      results.replaceChildren(table([
        ['When (IST)', (e) => fmtDT(e.occurred_at)], ['Event', (e) => badge(e.event_type, 'warn')],
        ['Reason', (e) => e.reason_code.replaceAll('_', ' ')],
        ['Details', (e) => h('details', {}, h('summary', {}, e.detail.end_reason || e.detail.detail || 'View recorded evidence'), h('pre', { class: 'sql' }, JSON.stringify(e.detail, null, 2)))],
      ], events.items, 'No stop or violation events recorded.'), pager(events, (offset) => load(offset).catch((e) => toast(e.message, 'bad'))));
    };
    box.append(h('p', { class: 'muted' }, 'Stops and entry violations remain in the record. A permit stop prevents new admission; an open entry can still record the worker’s exit.'), results);
    if (isRole('ADMIN', 'ENGINEER')) box.append(h('button', { type: 'button', onclick: async () => {
      try { const result = await api('POST', '/maintenance/sweep'); toast(`${result.stopped} permit(s) stopped after current checks.`); await load(); }
      catch (e) { toast(e.message, 'bad'); }
    } }, 'Check active permits now'));
    await load();
  };

  root.append(h('h2', {}, 'Permit details'), tabs([
    { id: 'crew', label: `Crew (${d.crew.length})`, render: crewTab }, { id: 'gear', label: `Gear (${d.gear.length})`, render: gearTab },
    { id: 'gas', label: `Observations (${d.readings.length})`, render: gasTab }, { id: 'readiness', label: 'Readiness', render: readinessTab },
    { id: 'receipts', label: 'Decision receipts', render: receiptsTab }, { id: 'entries', label: `Entries (${d.entries.length})`, render: entriesTab },
    { id: 'original', label: 'Original authorisation', render: originalTab },
    { id: 'safety', label: 'Safety history', render: safetyTab }, { id: 'end', label: 'End or stop', render: endTab }]));

  if (authorised) {
    const notice = h('div', { 'aria-live': 'polite' });
    decision.after(notice);
    const timer = setInterval(async () => {
      if (!root.isConnected) { clearInterval(timer); return; }
      try {
        const current = (await api('GET', `/permits/${id}`)).permit;
        if (current.status !== p.status) {
          clearInterval(timer);
          notice.replaceChildren(h('p', { class: 'banner bad' }, `Permit is now ${current.status}: ${current.end_reason || 'its status changed'}`),
            h('button', { type: 'button', onclick: reload }, 'Refresh permit and record exits'));
        }
      } catch { /* A temporary connection failure leaves the current form available. */ }
    }, 10000);
  }
}

const fmtDate10 = (s) => new Date(s + 'T00:00:00+05:30').toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium' });
