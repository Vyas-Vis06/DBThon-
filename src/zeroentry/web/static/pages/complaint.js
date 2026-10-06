import { api, badge, fmtDT, form, h, isRole, kv, options, table, toast } from '/static/app.js';

const REASONS = ['MACHINE_FAILED', 'NO_MACHINE_ACCESS', 'STRUCTURAL_CONSTRAINT', 'NO_MACHINE_AVAILABLE', 'OTHER'];
const RESOLUTIONS = [
  ['CLEARED', 'Cleared (machine or authorised manual entry)'], ['NO_BLOCKAGE_FOUND', 'No blockage found'],
  ['DUPLICATE_COMPLAINT', 'Duplicate complaint'], ['REFERRED_OUT', 'Referred to another agency'], ['WITHDRAWN', 'Withdrawn by complainant'],
];

export default async function (root, { params }) {
  const id = params.get('id');
  const c = await api('GET', `/complaints/${id}`);
  const writer = isRole('ADMIN', 'ENGINEER');
  const reload = () => location.reload();

  root.append(h('div', { class: 'row between' }, h('h1', {}, `Complaint #${c.complaint_id} `, badge(c.status)), h('a', { href: '/app/complaints' }, '← All complaints')),
    h('p', {}, c.description),
    kv([['Manhole', `${c.manhole.code} (${c.manhole.kind}, ${c.manhole.depth_m} m deep)`], ['Zone', c.manhole.ulb_name], ['Raised', fmtDT(c.raised_at)],
      c.resolved_at && ['Resolved', `${fmtDT(c.resolved_at)} as ${c.resolution_code.replaceAll('_', ' ')}`]]));

  for (const a of c.alerts) {
    root.append(h('p', { class: 'banner warn' }, 'Shadow-entry alert ', badge(a.status), ' ', h('a', { href: '/app/shadow#alerts' }, `#${a.alert_id}`), ': ', a.reason));
  }

  root.append(h('h2', {}, 'Jobs'));
  if (c.jobs.length === 0) root.append(h('p', { class: 'muted' }, 'No job has been created for this complaint yet.'));
  const machines = writer ? await options('/machines?limit=200', (m) => [m.machine_id, `${m.code} (${m.kind})`]) : [];

  for (const job of c.jobs) {
    const deployments = c.deployments.filter((d) => d.job_id === job.job_id);
    const waiver = c.waivers.find((w) => w.job_id === job.job_id);
    const permits = c.permits.filter((p) => p.job_id === job.job_id);
    const panel = h('div', { class: 'panel' },
      h('div', { class: 'row between' }, h('h3', {}, `Job #${job.job_id} · ${job.contractor_name}`), h('span', { class: 'row' }, badge(job.method), badge(job.status))),
      h('h3', {}, 'Machine deployments (clearance evidence)'),
      table([['Machine', (d) => `${d.machine_code} (${d.machine_kind})`], ['Started', (d) => fmtDT(d.started_at)], ['Ended', (d) => fmtDT(d.ended_at)],
        ['Outcome', (d) => d.outcome ? badge(d.outcome) : badge('IN PROGRESS', 'warn')], ['Recorded', (d) => fmtDT(d.recorded_at)],
        ['', (d) => (writer && !d.outcome) ? h('details', {}, h('summary', {}, 'Finish'), form([
          { name: 'ended_at', label: 'Ended', type: 'datetime', value: 'now', required: true },
          { name: 'outcome', label: 'Outcome', type: 'select', required: true, options: [{ value: 'CLEARED', label: 'CLEARED' }, { value: 'FAILED', label: 'FAILED' }] },
        ], async (v) => { await api('POST', `/deployments/${d.deploy_id}/finish`, v); reload(); }, { submit: 'Record outcome' })) : '']],
      deployments, 'No machine has been deployed. Mechanised cleaning must be tried first.'));

    if (writer) {
      panel.append(h('details', {}, h('summary', {}, 'Deploy a machine'), form([
        { name: 'machine_id', label: 'Machine', type: 'select', options: machines, required: true, int: true },
        { name: 'started_at', label: 'Started', type: 'datetime', value: 'now', required: true },
        { name: 'ended_at', label: 'Ended (if finished)', type: 'datetime' },
        { name: 'outcome', label: 'Outcome (if finished)', type: 'select', options: [{ value: 'CLEARED', label: 'CLEARED' }, { value: 'FAILED', label: 'FAILED' }] },
      ], async (v) => { await api('POST', `/jobs/${job.job_id}/deployments`, v); reload(); }, { submit: 'Record deployment' })));
    }

    panel.append(h('h3', {}, 'Written mechanisation waiver'));
    if (waiver) {
      panel.append(h('p', {}, badge(waiver.reason_code), ' approved ', fmtDT(waiver.approved_at)), h('blockquote', {}, waiver.justification));
    } else {
      panel.append(h('p', { class: 'muted' }, 'None. No entry permit can be drafted until the Responsible Sanitation Authority records in writing why no machine can do the job.'));
      if (isRole('ENGINEER')) {
        panel.append(h('details', {}, h('summary', {}, 'File a waiver (engineers only)'), form([
          { name: 'reason_code', label: 'Reason', type: 'select', required: true, options: REASONS.map((r) => ({ value: r, label: r.replaceAll('_', ' ') })),
            hint: 'MACHINE FAILED needs a recorded failed deployment on this complaint.' },
          { name: 'justification', label: 'Justification (at least 50 characters)', type: 'textarea', required: true, wide: true, attrs: { minlength: 50 } },
        ], async (v) => { await api('POST', `/jobs/${job.job_id}/waiver`, v); toast('Waiver recorded; the job is now a manual exception.'); reload(); }, { submit: 'Approve waiver' })));
      }
    }

    panel.append(h('h3', {}, 'Entry permits'),
      permits.length ? h('ul', {}, permits.map((p) => h('li', {}, h('a', { href: '/app/permit?id=' + p.permit_id }, 'Permit #' + p.permit_id), ' ', badge(p.status)))) : h('p', { class: 'muted' }, 'No permit.'));
    if (isRole('SUPERVISOR') && waiver) {
      panel.append(h('button', { type: 'button', class: 'primary', onclick: async () => {
        try { const p = await api('POST', '/permits', { job_id: job.job_id }); location.assign('/app/permit?id=' + p.permit_id); } catch (e) { toast(e.message, 'bad'); }
      } }, 'Draft an entry permit'));
    }
    root.append(panel);
  }

  if (writer) {
    const contractors = await options('/contractors?limit=200', (k) => [k.contractor_id, `${k.name} · ${k.status}`]);
    root.append(h('details', { class: 'panel' }, h('summary', {}, 'Create a job (assign a contractor)'), form([
      { name: 'contractor_id', label: 'Contractor', type: 'select', required: true, int: true, options: contractors,
        hint: 'A suspended or blacklisted contractor is refused by the database.' },
    ], async (v) => { await api('POST', '/jobs', { complaint_id: c.complaint_id, contractor_id: v.contractor_id }); reload(); }, { submit: 'Create job' })));

    if (c.status !== 'RESOLVED') {
      root.append(h('h2', {}, 'Resolve this complaint'), h('div', { class: 'panel' },
        h('p', { class: 'muted' }, 'Resolving is not blocked when no clearance evidence exists: the gap is exactly what the absence scan looks for.'),
        form([{ name: 'resolution_code', label: 'Resolution', type: 'select', required: true, options: RESOLUTIONS.map(([value, label]) => ({ value, label })) }],
          async (v) => {
            const r = await api('POST', `/complaints/${c.complaint_id}/resolve`, v);
            if (r.warning) { sessionStorage.setItem('flash', r.warning); }
            reload();
          }, { submit: 'Resolve complaint' })));
    }
  }
  const flash = sessionStorage.getItem('flash');
  if (flash) { sessionStorage.removeItem('flash'); root.prepend(h('p', { class: 'banner warn' }, flash)); }
}
