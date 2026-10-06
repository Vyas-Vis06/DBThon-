import { api, badge, form, guard, h, isRole, options, pager, qs, table, tabs, toast } from '/static/app.js';

// One generic list / search / create / edit / delete screen per master-data table. The server enforces who may write.
const STATUS = (...v) => v.map((s) => ({ value: s, label: s }));
const today = new Date().toISOString().slice(0, 10);
const until = (d) => d >= today ? d : h('span', { class: 'badge bad' }, 'expired ' + d);

async function resources() {
  const ulbs = await options('/ulbs?limit=200', (u) => [u.ulb_id, u.name]).catch(() => []);
  const contractors = await options('/contractors?limit=200', (c) => [c.contractor_id, c.name]).catch(() => []);
  const named = (list) => (id) => (list.find((o) => o.value === id) || {}).label || id;
  return [
    { id: 'workers', label: 'Workers', path: '/workers', write: ['ADMIN', 'ENGINEER'], remove: ['ADMIN'], search: 'NAMASTE ID or name',
      columns: [['Name', (r) => r.full_name], ['NAMASTE ID', (r) => r.namaste_id], ['Contractor', (r) => named(contractors)(r.contractor_id)],
        ['Medical fit until', (r) => until(r.medical_fit_until)], ['Trained until', (r) => until(r.trained_until)], ['Active', (r) => r.is_active ? 'yes' : badge('NO', 'bad')]],
      fields: [{ name: 'contractor_id', label: 'Contractor', type: 'select', int: true, options: contractors, required: true }, { name: 'full_name', label: 'Full name', required: true },
        { name: 'namaste_id', label: 'NAMASTE ID', required: true }, { name: 'medical_fit_until', label: 'Medically fit until', type: 'date', required: true },
        { name: 'trained_until', label: 'Trained until', type: 'date', required: true }, { name: 'is_active', label: 'Active', type: 'checkbox', value: true }] },
    { id: 'contractors', label: 'Contractors', path: '/contractors', write: ['ADMIN', 'ENGINEER'], remove: ['ADMIN'], search: 'name or licence number',
      columns: [['Name', (r) => r.name], ['Licence', (r) => r.licence_no], ['Licence valid until', (r) => until(r.licence_valid_until)], ['Status', (r) => badge(r.status)]],
      fields: [{ name: 'name', label: 'Name', required: true }, { name: 'licence_no', label: 'Licence number', required: true },
        { name: 'licence_valid_until', label: 'Licence valid until', type: 'date', required: true },
        { name: 'status', label: 'Status', type: 'select', options: STATUS('ACTIVE', 'SUSPENDED', 'BLACKLISTED'), required: true,
          hint: 'Only an administrator can blacklist or lift a blacklisting.' }] },
    { id: 'manholes', label: 'Manholes', path: '/manholes', write: ['ADMIN', 'ENGINEER'], remove: ['ADMIN'], search: 'code',
      columns: [['Code', (r) => r.code], ['Kind', (r) => r.kind], ['Depth (m)', (r) => r.depth_m], ['Zone', (r) => named(ulbs)(r.ulb_id)], ['Location', (r) => `${r.lat}, ${r.lng}`]],
      fields: [{ name: 'ulb_id', label: 'Zone', type: 'select', int: true, options: ulbs, required: true }, { name: 'code', label: 'Code', required: true },
        { name: 'kind', label: 'Kind', type: 'select', options: STATUS('SEWER', 'SEPTIC'), required: true }, { name: 'depth_m', label: 'Depth (m)', type: 'number', step: '0.01', min: 0.01, required: true },
        { name: 'lat', label: 'Latitude', type: 'number', step: '0.000001', required: true }, { name: 'lng', label: 'Longitude', type: 'number', step: '0.000001', required: true },
        { name: 'address', label: 'Address', wide: true }] },
    { id: 'machines', label: 'Machines', path: '/machines', write: ['ADMIN', 'ENGINEER'], remove: ['ADMIN'],
      columns: [['Code', (r) => r.code], ['Kind', (r) => r.kind], ['Zone', (r) => named(ulbs)(r.ulb_id)], ['Status', (r) => badge(r.status, r.status === 'AVAILABLE' ? 'ok' : 'warn')]],
      fields: [{ name: 'ulb_id', label: 'Zone', type: 'select', int: true, options: ulbs, required: true }, { name: 'code', label: 'Code', required: true },
        { name: 'kind', label: 'Kind', type: 'select', options: STATUS('JETTING', 'SUCTION', 'ROBOT'), required: true },
        { name: 'status', label: 'Status', type: 'select', options: STATUS('AVAILABLE', 'IN_USE', 'MAINTENANCE'), required: true }] },
    { id: 'detectors', label: 'Gas detectors', path: '/detectors', write: ['ADMIN'], remove: ['ADMIN'], search: 'serial',
      columns: [['Serial', (r) => r.serial_no], ['Model', (r) => r.model], ['Calibration valid until', (r) => until(r.calibration_valid_until)]],
      fields: [{ name: 'serial_no', label: 'Serial number', required: true }, { name: 'model', label: 'Model', required: true },
        { name: 'calibration_valid_until', label: 'Calibration valid until', type: 'date', required: true }] },
    { id: 'gear', label: 'Gear catalogue', path: '/gear-items', write: ['ADMIN'], remove: ['ADMIN'], key: 'gear_code',
      columns: [['Code', (r) => r.gear_code], ['Item', (r) => r.name], ['Statutory', (r) => r.statutory ? badge('MANDATORY', 'bad') : 'optional'], ['Legal reference', (r) => r.legal_ref || '']],
      fields: [{ name: 'gear_code', label: 'Code (UPPER_CASE)', required: true }, { name: 'name', label: 'Item', required: true },
        { name: 'statutory', label: 'Statutory: every entrant must hold it', type: 'checkbox' }, { name: 'legal_ref', label: 'Legal reference', wide: true }] },
    { id: 'zones', label: 'Zones (ULBs)', path: '/ulbs', write: ['ADMIN'], remove: ['ADMIN'], search: 'name',
      columns: [['Name', (r) => r.name], ['District', (r) => r.district], ['State', (r) => r.state]],
      fields: [{ name: 'name', label: 'Name', required: true }, { name: 'district', label: 'District', required: true }, { name: 'state', label: 'State', required: true }] },
  ];
}

function screen(r) {
  return async (box) => {
    const writer = r.write.some((x) => isRole(x));
    const filters = { q: '', offset: 0 };
    const results = h('div');
    const load = guard(async () => {
      const data = await api('GET', r.path + qs({ q: filters.q, limit: 25, offset: filters.offset }));
      const idOf = (row) => row[r.key] ?? row[Object.keys(row)[0]];
      const cols = [...r.columns];
      if (writer || r.remove.some((x) => isRole(x))) {
        cols.push(['', (row) => h('span', { class: 'row' },
          writer && h('details', {}, h('summary', {}, 'Edit'), form(r.fields.map((f) => ({ ...f, required: false, value: row[f.name] })),
            async (v) => { await api('PATCH', `${r.path}/${idOf(row)}`, v); toast('Saved.'); load(); }, { submit: 'Save changes' })),
          r.remove.some((x) => isRole(x)) && h('button', { type: 'button', class: 'danger', onclick: guard(async () => {
            if (!confirm('Delete this record? The database refuses if anything still refers to it.')) return;
            await api('DELETE', `${r.path}/${idOf(row)}`); toast('Deleted.'); load();
          }) }, 'Delete'))]);
      }
      results.replaceChildren(table(cols, data.items, 'No records.'), pager(data, (o) => { filters.offset = o; load(); }));
    });
    if (r.search) box.append(h('div', { class: 'panel' }, form([{ name: 'q', label: 'Search', hint: r.search }], async (v) => { filters.q = v.q || ''; filters.offset = 0; await load(); }, { submit: 'Search' })));
    box.append(results);
    if (writer) box.append(h('details', { class: 'panel' }, h('summary', {}, 'Add a new record'),
      form(r.fields, async (v) => { await api('POST', r.path, v); toast('Created.'); load(); }, { submit: 'Create' })));
    await load();
  };
}

export default async function (root) {
  root.append(h('h1', {}, 'Registry'), h('p', { class: 'muted' }, 'Master data. Uniqueness, keys and every business rule are enforced by the database, so a refusal here quotes the rule.'));
  const visible = isRole('CONTRACTOR', 'WORKER') ? ['workers', 'contractors'] : null;
  const all = await resources();
  root.append(tabs(all.filter((r) => !visible || visible.includes(r.id)).map((r) => ({ id: r.id, label: r.label, render: screen(r) }))));
}
