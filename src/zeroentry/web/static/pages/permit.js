import { ago, api, badge, clauseList, fmtDT, form, h, isRole, kv, localIST, options, pager, table, tabs, toast } from '/static/app.js';

const BANNER = {
  AUTHORISED: ['ok', 'ENTRY AUTHORISED'], CLOSED: ['warn', 'PERMIT CLOSED'], ABORTED: ['bad', 'PERMIT ABORTED (stop-work)'], CANCELLED: ['warn', 'PERMIT CANCELLED'],
};

export default async function (root, { params }) {
  const id = params.get('id');
  const d = await api('GET', `/permits/${id}`);
  const p = d.permit;
  const supervisor = isRole('SUPERVISOR');
  const decide = isRole('SUPERVISOR', 'ENGINEER');
  const staff = isRole('ADMIN', 'ENGINEER', 'SUPERVISOR', 'AUDITOR');
  const draft = p.status === 'DRAFT';
  const authorised = p.status === 'AUTHORISED';
  const canRecordExit = authorised || p.status === 'ABORTED';
  const reload = () => location.reload();

  root.append(
    h('div', { class: 'row between' }, h('h1', {}, `Entry permit #${p.permit_id} `, badge(p.status)), h('a', { href: '/app/permits' }, '← All permits')),
    kv([['Manhole', `${d.complaint.manhole_code} (${d.complaint.manhole_kind}, ${d.complaint.depth_m} m)`], ['Zone', d.complaint.ulb_name],
      ['Contractor', d.job.contractor_name || '–'], ['Complaint', h('a', { href: '/app/complaint?id=' + d.complaint.complaint_id }, '#' + d.complaint.complaint_id)],
      ['Mechanisation waiver', d.waiver ? d.waiver.reason_code.replaceAll('_', ' ') : 'none'], ['Created', fmtDT(p.created_at)],
      p.authorised_at && ['Authorised', fmtDT(p.authorised_at)], p.valid_until && ['Valid until', fmtDT(p.valid_until)],
      p.ended_at && ['Ended', fmtDT(p.ended_at)], p.end_reason && ['Reason', p.end_reason]]));

  // ---- the decision -------------------------------------------------------------------------------------------------
  const decision = h('div', { class: 'panel' });
  root.append(h('h2', {}, 'Entry decision'), decision);

  const showChecklist = (clauses, verdict) => {
    const failing = clauses.filter((c) => !c.passed);
    decision.replaceChildren(
      verdict || h('p', { class: 'banner ' + (failing.length ? 'bad' : 'ok') },
        failing.length ? `NOT READY: ${failing.length} of ${clauses.length} checks fail right now.` : `READY: all ${clauses.length} configured checks pass right now.`),
      clauseList(clauses), decisionButtons());
  };

  function decisionButtons() {
    if (!draft || !decide) return h('p', { class: 'small muted' }, draft ? 'Only a supervisor or engineer can ask for authorisation.' : '');
    return h('div', { class: 'row' },
      h('button', { type: 'button', onclick: recheck }, 'Re-check the clauses'),
      h('button', { type: 'button', class: 'primary', onclick: authorise }, 'Ask the database to authorise entry'),
      h('span', { class: 'small muted' }, 'Gas readings go stale after 15 minutes; re-check before asking.'));
  }

  async function recheck() {
    try { const r = await api('GET', `/permits/${id}/clauses`); showChecklist(r.clauses); toast(r.ready_to_authorise ? 'Every clause passes.' : 'Some clauses still fail.', r.ready_to_authorise ? 'ok' : 'bad'); }
    catch (e) { toast(e.message, 'bad'); }
  }

  async function authorise() {
    try {
      const r = await api('POST', `/permits/${id}/authorise`);
      if (r.authorised) {
        showChecklist(r.clauses, h('p', { class: 'banner ok' }, 'AUTHORISED: every configured check passed. The original decision is saved; crew and gear are now frozen.'));
        setTimeout(reload, 1500);
      } else {
        showChecklist(r.clauses, h('p', { class: 'banner bad' }, `DENIED: ${r.failed.length} check(s) not satisfied: ${r.failed.join(', ')}`));
      }
    } catch (e) { toast(e.message, 'bad'); }
  }

  if (draft && d.clauses) showChecklist(d.clauses);
  else {
    const [kind, text] = BANNER[p.status] || ['warn', p.status];
    decision.replaceChildren(...[h('p', { class: 'banner ' + kind }, text + (p.status === 'AUTHORISED' ? `: valid until ${fmtDT(p.valid_until)}` : '')),
      p.end_reason && h('p', {}, 'Reason recorded: ', h('em', {}, p.end_reason))].filter(Boolean));   // replaceChildren(null) would print "null"
  }

  // ---- crew, gear, readings, entries, ending -------------------------------------------------------------------------
  const entrants = d.crew.filter((w) => w.crew_role === 'ENTRANT');
  const today = new Date().toISOString().slice(0, 10);
  const fit = (date) => date >= today ? fmtDate10(date) : h('span', { class: 'badge bad' }, 'expired ' + fmtDate10(date));

  const crewTab = async (box) => {
    box.append(table([
      ['Name', (w) => w.full_name], ['NAMASTE ID', (w) => w.namaste_id], ['Role', (w) => badge(w.crew_role, w.crew_role === 'ENTRANT' ? 'info' : 'grey')],
      ['Medically fit until', (w) => fit(w.medical_fit_until)], ['Trained until', (w) => fit(w.trained_until)],
      ['', (w) => (draft && supervisor) ? h('button', { type: 'button', class: 'danger', onclick: async () => {
        try { await api('DELETE', `/permits/${id}/crew/${w.worker_id}`); reload(); } catch (e) { toast(e.message, 'bad'); } } }, 'Remove') : ''],
    ], d.crew, 'No crew yet. A permit needs at least one entrant, one standby (top man) who does not enter, and a supervisor: three or more people.'));
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
    const catalogue = staff ? (await api('GET', '/gear-items?limit=200')).items : [];
    const statutory = catalogue.filter((g) => g.statutory);
    if (statutory.length && entrants.length) {
      box.append(h('p', { class: 'muted' }, 'Every ENTRANT must hold every statutory item (relational division). A missing cell fails the “GEAR_ALL” clause.'),
        h('div', { class: 'scroll' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, 'Entrant'), statutory.map((g) => h('th', { scope: 'col' }, g.name)))),
          h('tbody', {}, entrants.map((w) => h('tr', {}, h('td', {}, w.full_name),
            statutory.map((g) => { const issue = d.gear.find((x) => x.worker_id === w.worker_id && x.gear_code === g.gear_code);
              return h('td', {}, issue ? [issue.serial_no, (draft && supervisor) && h('button', { type: 'button', class: 'link', onclick: async () => {
                try { await api('DELETE', `/permits/${id}/gear/${issue.issue_id}`); reload(); } catch (e) { toast(e.message, 'bad'); } } }, ' ✕')] : badge('MISSING', 'bad')); })))))));
    } else {
      box.append(table([['Worker', (g) => (d.crew.find((w) => w.worker_id === g.worker_id) || {}).full_name], ['Item', (g) => g.gear_name], ['Serial', (g) => g.serial_no],
        ['Statutory', (g) => g.statutory ? 'yes' : 'no']], d.gear, 'No gear issued.'));
    }
    if (draft && supervisor && d.crew.length) {
      box.append(h('h3', {}, 'Issue an item to a crew member'), form([
        { name: 'worker_id', label: 'Crew member', type: 'select', required: true, int: true, options: d.crew.map((w) => ({ value: w.worker_id, label: `${w.full_name} (${w.crew_role})` })) },
        { name: 'gear_code', label: 'Item', type: 'select', required: true, options: catalogue.map((g) => ({ value: g.gear_code, label: g.name + (g.statutory ? ' *' : '') })), hint: '* statutory' },
        { name: 'serial_no', label: 'Serial number of the item handed over', required: true },
      ], async (v) => { await api('POST', `/permits/${id}/gear`, v); reload(); }, { submit: 'Issue' }));
      box.append(h('details', {}, h('summary', {}, 'Quick issue: all missing statutory items to one entrant'), form([
        { name: 'worker_id', label: 'Entrant', type: 'select', required: true, int: true, options: entrants.map((w) => ({ value: w.worker_id, label: w.full_name })) },
        { name: 'prefix', label: 'Serial prefix', required: true, hint: 'Serials become PREFIX-ITEMCODE. A person still asserts they handed the items over.' },
      ], async (v) => {
        const missing = statutory.filter((g) => !d.gear.some((x) => x.worker_id === v.worker_id && x.gear_code === g.gear_code));
        for (const g of missing) await api('POST', `/permits/${id}/gear`, { worker_id: v.worker_id, gear_code: g.gear_code, serial_no: `${v.prefix}-${g.gear_code}` });
        toast(`${missing.length} item(s) issued.`); reload();
      }, { submit: 'Issue all missing' })));
    }
  };

  const gasTab = async (box) => {
    box.append(h('p', { class: 'muted' }, 'For each depth the LATEST reading governs: at most 15 minutes old, from a detector calibrated that day, O₂ 19.5–21 %, H₂S and combustibles below their limits. Readings cannot be edited or deleted.'),
      table([['Taken (IST)', (r) => [fmtDT(r.taken_at), ' ', h('span', { class: 'small muted' }, ago(r.taken_at))]], ['Depth', (r) => badge(r.depth_level, 'info')],
        ['O₂ %', (r) => r.o2_pct], ['H₂S ppm', (r) => r.h2s_ppm], ['LEL %', (r) => r.lel_pct], ['CO ppm', (r) => r.co_ppm], ['Detector', (r) => r.detector_serial],
        ['Signed off by', (r) => r.recorded_by_name]], d.readings, 'No readings logged yet.'));
    if ((draft || authorised) && decide) {
      const detectors = await options('/detectors?limit=200', (x) => [x.detector_id, `${x.serial_no} · calibrated until ${x.calibration_valid_until}`]);
      const f = form([
        { name: 'detector_id', label: 'Detector', type: 'select', required: true, int: true, options: detectors },
        { name: 'depth_level', label: 'Depth', type: 'select', required: true, options: ['TOP', 'MID', 'BOTTOM'].map((x) => ({ value: x, label: x })) },
        { name: 'o2_pct', label: 'O₂ %', type: 'number', step: '0.1', required: true, min: 0, max: 100 },
        { name: 'h2s_ppm', label: 'H₂S ppm', type: 'number', step: '0.01', required: true, min: 0 },
        { name: 'lel_pct', label: 'Combustibles % LEL', type: 'number', step: '0.01', required: true, min: 0, max: 100 },
        { name: 'co_ppm', label: 'CO ppm', type: 'number', step: '0.01', required: true, min: 0 },
      ], async (v) => { await api('POST', `/permits/${id}/readings`, v); reload(); }, { submit: 'Sign off this reading' });
      box.append(h('h3', {}, 'Log a reading (your digital sign-off)'), f, h('button', { type: 'button', class: 'link', onclick: () => {
        for (const [k, val] of Object.entries({ o2_pct: 20.9, h2s_ppm: 0, lel_pct: 0, co_ppm: 0 })) f.elements[k].value = val;
      } }, 'Fill typical fresh-air values (demo convenience)'));
    }
  };

  const entriesTab = async (box) => {
    box.append(h('p', { class: 'muted' }, 'A new entry needs current authorisation, an ENTRANT, a valid permit, and daylight. No worker can have overlapping entries. A 90-minute stretch requires a 30-minute rest; if an exit is reported late, it is still recorded with violation evidence. Open entries remain closable after a permit stop.'),
      table([['Worker', (e) => `${e.worker_name} (${e.namaste_id})`], ['Entered', (e) => fmtDT(e.entered_at)], ['Exited', (e) => e.open ? badge('INSIDE NOW', 'warn') : fmtDT(e.exited_at)],
        ['Minutes', (e) => e.minutes ?? ''],
        ['', (e) => (e.open && supervisor && canRecordExit) ? h('details', {}, h('summary', {}, p.status === 'ABORTED' ? 'Record exit after stop' : 'Record exit'), form([
          { name: 'exited_at', label: 'Exited', type: 'datetime', value: 'now', required: true }],
          async (v) => { await api('POST', `/permits/${id}/entries/${e.entry_id}/exit`, v); reload(); }, { submit: 'Record exit' })) : '']], d.entries, 'No one has entered.'));
    if (authorised && supervisor) {
      box.append(h('h3', {}, 'Log an entry'), form([
        { name: 'worker_id', label: 'Entrant', type: 'select', required: true, int: true, options: d.crew.map((w) => ({ value: w.worker_id, label: `${w.full_name} (${w.crew_role})` })) },
        { name: 'entered_at', label: 'Entered (India time)', type: 'datetime', required: true,
          value: localIST(new Date(Math.max(Date.now(), new Date(p.authorised_at).getTime() + 1000))), hint: 'Cannot be earlier than the authorisation instant.' },
        { name: 'exited_at', label: 'Exited (leave empty while inside)', type: 'datetime' },
      ], async (v) => { await api('POST', `/permits/${id}/entries`, v); reload(); }, { submit: 'Log entry' }));
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
    { id: 'gas', label: `Gas readings (${d.readings.length})`, render: gasTab }, { id: 'entries', label: `Entries (${d.entries.length})`, render: entriesTab },
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
