import { api, badge, fmtDT, h, table } from '/static/app.js';

const LABS = [
  ['LAB1-DDL-DML', 'DDL and DML', 'Schema changes and stateful create/read/update/archive examples.'],
  ['LAB2-CONSTRAINTS', 'Constraints', 'Primary and foreign keys, checks, uniqueness, resource exclusions, and rejected invalid states.'],
  ['LAB3-ROW-FUNCTIONS', 'Single-row functions', 'Time boundaries, normalization, expiry and derived status.'],
  ['LAB4-OPERATORS-GROUPS', 'Operators and group functions', 'NULL handling, filters, grouped evidence summaries and aggregates.'],
  ['LAB5-SUBQUERIES-VIEWS-JOINS', 'Subqueries, views and joins', 'Relational division, anti-joins, linked evidence and review read models.'],
  ['LAB6-FUNCTIONS-PROCEDURES-CURSORS-TRIGGERS', 'Functions, procedures, cursors and triggers', 'Decision routines, atomic incident intake, audit/revision triggers and bounded report traversal.'],
];

function safeSourceLink(source) {
  const url = source.source_url || source.url;
  if (!url || !/^https?:\/\//i.test(url)) return source.title || source.name || 'source reference';
  return h('a', { href: url, target: '_blank', rel: 'noopener noreferrer' }, source.title || source.name || url);
}

export default async function (root) {
  root.append(h('h1', {}, 'Judge evidence'),
    h('p', { class: 'muted' }, 'This page shows only evidence returned by the server. Missing run manifests, artifacts, or measurements are marked NOT YET MEASURED.'),
    h('p', { class: 'banner warn' }, 'The prototype tests software decisions against labelled synthetic cases. It does not establish physical safety, prevent deaths, prove fraud, or show that compensation was paid.'));

  const content = h('div', { role: 'status', 'aria-live': 'polite' }, h('p', { class: 'muted' }, 'Loading evidence manifest from the server…'));
  root.append(content);
  let evidence;
  try { evidence = await api('GET', '/judge/evidence'); }
  catch (error) {
    content.replaceChildren(h('p', { class: 'banner bad', role: 'alert' }, `Judge evidence is unavailable: ${error.message}. No mock metrics or evidence links are displayed.`));
    return;
  }

  const labs = evidence.labs || evidence.lab_demos || [];
  const labById = new Map(labs.map((item) => [String(item.id || item.code || item.lab_id).toUpperCase(), item]));
  content.replaceChildren(h('h2', {}, 'Six database lab demonstrations'),
    h('p', { class: 'small muted' }, 'Status comes from the current manifest; a topic description alone is not evidence that its script was run.'),
    h('div', { class: 'grid' }, LABS.map(([id, title, summary]) => {
      const result = labById.get(id) || labById.get(id.replaceAll('-', '_'));
      const status = result?.status || 'NOT_YET_MEASURED';
      return h('article', { class: 'panel' }, h('div', { class: 'row between' }, h('h3', {}, title), badge(status, status === 'PASS' || status === 'VERIFIED' ? 'info' : 'warn')),
        h('p', {}, summary),
        h('p', { class: 'small muted' }, `Evidence ID: ${id}`),
        result?.artifact_path && h('p', { class: 'small' }, 'Artifact path: ', h('code', {}, result.artifact_path)),
        result?.run_id && h('p', { class: 'small' }, 'Run: ', result.run_id),
        result?.git_sha && h('p', { class: 'small' }, 'Commit: ', result.git_sha),
        result?.measured_at && h('p', { class: 'small' }, 'Run time: ', fmtDT(result.measured_at)),
        result?.summary && h('p', {}, result.summary));
    })));

  const measurements = evidence.measurements || {};
  const runs = measurements.runs || measurements.results || [];
  content.append(h('h2', {}, 'Measured results'),
    h('p', { class: `banner ${measurements.status === 'MEASURED' || measurements.status === 'VERIFIED' ? 'neutral' : 'warn'}` },
      measurements.status || 'NOT_YET_MEASURED', ' · ', measurements.scope || 'No measurement scope supplied.'),
    runs.length ? table([['Measure', (r) => r.metric || r.name || 'not named'], ['Result', (r) => r.value ?? 'NOT_YET_MEASURED'], ['Unit', (r) => r.unit || 'not supplied'],
      ['Sample size', (r) => r.sample_size ?? 'not supplied'], ['Dataset / variant', (r) => r.scope || r.scenario || 'not supplied'],
      ['Run', (r) => r.run_id || measurements.run_id || 'not supplied'], ['Commit', (r) => r.git_sha || measurements.git_sha || 'not supplied']], runs,
    'No measured values were returned. NOT_YET_MEASURED.' ) : h('p', { class: 'panel' }, 'NOT_YET_MEASURED. No numeric values are available in the server manifest.'),
    measurements.limitations && h('p', { class: 'small muted' }, measurements.limitations));

  const runtime = evidence.runtime || {};
  content.append(h('h2', {}, 'Execution metadata'), table([
    ['Field', (row) => row.name], ['Value', (row) => row.value ?? 'not supplied'],
  ], [
    { name: 'Runtime mode', value: runtime.mode || runtime.source_mode || 'unknown' },
    { name: 'Commit', value: runtime.git_sha || runtime.commit || 'not supplied' },
    { name: 'Run ID', value: runtime.run_id || 'not supplied' },
    { name: 'Generated', value: fmtDT(runtime.generated_at) || 'not supplied' },
    { name: 'Database', value: runtime.database_version || 'not supplied' },
    { name: 'Policy scope', value: runtime.policy_mode || 'not supplied' },
  ]));

  const sources = evidence.sources || [];
  content.append(h('h2', {}, 'Sources and research'),
    h('p', { class: 'small muted' }, 'Source classification and applicability are shown as supplied by the server. The source register supports design interpretation; it is not a legal determination.'),
    table([['Category', (s) => badge(s.source_category || s.source_type || 'UNCLASSIFIED', 'info')], ['Source', safeSourceLink],
      ['Locator / version', (s) => `${s.source_locator || s.locator || 'not supplied'}${s.source_version || s.version ? ` · ${s.source_version || s.version}` : ''}`],
      ['Applicability / limitation', (s) => s.applicability || s.limitation || 'not supplied'], ['Verified / retrieved', (s) => s.verified_on || s.retrieved_on || 'not supplied']], sources,
    'No source records were returned by the evidence service.'));

  if (evidence.er_diagram_url || evidence.schema_url) {
    content.append(h('h2', {}, 'Schema references'), h('div', { class: 'row' },
      evidence.er_diagram_url && h('a', { class: 'btn', href: evidence.er_diagram_url }, 'Open ER diagram'),
      evidence.schema_url && h('a', { class: 'btn', href: evidence.schema_url }, 'Open schema reference')));
  } else {
    content.append(h('p', { class: 'small muted' }, 'ER diagram and schema reference links were not supplied in the server manifest.'));
  }
}
