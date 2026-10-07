import { api, badge, fmtDT, form, guard, h, isRole, options, pager, qs, table, tabs, toast } from '/static/app.js';

const ROLES = ['ADMIN', 'ENGINEER', 'SUPERVISOR', 'WORKER', 'CONTRACTOR', 'AUDITOR'].map((r) => ({ value: r, label: r }));

export default async function (root) {
  const admin = isRole('ADMIN');
  root.append(h('h1', {}, 'Administration'));

  const usersTab = async (box) => {
    const [contractors, workers, ulbs] = await Promise.all([options('/contractors?limit=200', (c) => [c.contractor_id, c.name]),
      options('/workers?limit=200', (w) => [w.worker_id, `${w.full_name} · ${w.namaste_id}`]), options('/ulbs?limit=200', (u) => [u.ulb_id, u.name])]);
    const filters = { offset: 0 };
    const results = h('div');
    const patch = (u, body, msg) => guard(async () => { await api('PATCH', `/admin/users/${u.user_id}`, body); toast(msg); load(); });
    const load = guard(async () => {
      const data = await api('GET', '/admin/users' + qs({ limit: 20, offset: filters.offset }));
      results.replaceChildren(table([['#', (u) => u.user_id], ['Email', (u) => u.email], ['Name', (u) => u.full_name], ['Role', (u) => badge(u.role, 'info')],
        ['Active', (u) => u.is_active ? 'yes' : badge('DEACTIVATED', 'bad')], ['Locked', (u) => (u.locked_until && new Date(u.locked_until) > new Date()) ? badge('LOCKED', 'warn') : ''],
        ['', (u) => h('span', { class: 'row' },
          h('button', { type: 'button', onclick: patch(u, { is_active: !u.is_active }, u.is_active ? 'User deactivated and signed out.' : 'User reactivated.') }, u.is_active ? 'Deactivate' : 'Reactivate'),
          h('button', { type: 'button', onclick: patch(u, { unlock: true }, 'Account unlocked.') }, 'Unlock'),
          h('details', {}, h('summary', {}, 'Reset password'), form([{ name: 'new_password', label: 'New password (12+ characters)', type: 'password', required: true, attrs: { autocomplete: 'new-password' } }],
            async (v) => { await api('PATCH', `/admin/users/${u.user_id}`, v); toast('Password reset; the user was signed out everywhere.'); }, { submit: 'Reset' })))]],
        data.items), pager(data, (o) => { filters.offset = o; load(); }));
    });
    box.append(results, h('h2', {}, 'Create a user'), h('div', { class: 'panel' },
      h('p', { class: 'muted' }, 'CONTRACTOR users must be linked to a contractor, WORKER users to a worker; other roles to neither. Passwords need 12+ characters, mixed case and a digit.'),
      form([{ name: 'email', label: 'Email', type: 'email', required: true }, { name: 'full_name', label: 'Full name', required: true },
        { name: 'role', label: 'Role', type: 'select', required: true, options: ROLES }, { name: 'password', label: 'Initial password', type: 'password', required: true, attrs: { autocomplete: 'new-password' } },
        { name: 'ulb_id', label: 'Zone (optional)', type: 'select', int: true, options: ulbs }, { name: 'contractor_id', label: 'Contractor (CONTRACTOR role)', type: 'select', int: true, options: contractors },
        { name: 'worker_id', label: 'Worker (WORKER role)', type: 'select', int: true, options: workers }],
      async (v) => { await api('POST', '/admin/users', v); toast('User created.'); load(); }, { submit: 'Create user' })));
    await load();
  };

  const rulesTab = async (box) => {
    const [data, sources] = await Promise.all([api('GET', '/rules'), api('GET', '/policy-sources')]);
    const sourceByCode = new Map(sources.items.map((s) => [s.source_code, s]));
    const history = h('div');
    const showHistory = async (key, offset = 0) => {
      try {
        const revisions = await api('GET', `/rules/${encodeURIComponent(key)}/history?limit=10&offset=${offset}`);
        history.replaceChildren(h('h3', {}, `Policy history: ${key}`), table([
          ['Revision', (r) => r.revision], ['Value', (r) => `${r.value} ${r.unit}`], ['Effective from', (r) => fmtDT(r.effective_at)],
          ['Changed by', (r) => r.actor_user_id ? '#' + r.actor_user_id : 'migration baseline'], ['Reason', (r) => r.change_reason],
        ], revisions.items), pager(revisions, (offset) => showHistory(key, offset)));
      } catch (e) { toast(e.message, 'bad'); }
    };
    box.append(h('p', { class: 'muted' }, 'Law, court directions, guidance and product policy have separate source labels. Every value change creates a revision with its reason, actor and time. History starts at the provenance migration; earlier revisions are unavailable.'),
      table([['Key', (r) => h('code', {}, r.param_key)], ['Value', (r) => [h('strong', {}, Number(r.value)), ' ', r.unit]], ['Meaning', (r) => r.description],
        ['Basis', (r) => badge(sourceByCode.get(r.source_code)?.source_type || 'UNCLASSIFIED', r.is_assumption ? 'warn' : 'info')],
        ['Legal reference', (r) => [r.legal_ref, ' ', r.is_assumption && badge('ASSUMPTION', 'warn')]], ['Updated', (r) => fmtDT(r.updated_at)],
        ['Revision', (r) => h('button', { type: 'button', class: 'link', onclick: () => showHistory(r.param_key) }, `View revision ${r.revision}`)],
        ['', (r) => admin ? h('details', {}, h('summary', {}, 'Change'), form([{ name: 'value', label: 'New value', type: 'number', step: 'any', required: true },
          { name: 'reason', label: 'Reason for changing this policy', type: 'textarea', required: true, attrs: { minlength: 10, maxlength: 1000 } }],
          async (v) => { await api('PATCH', `/rules/${r.param_key}`, v); toast('Rule changed and audited.'); location.reload(); }, { submit: 'Change rule' })) : '']], data.items), history,
      h('details', {}, h('summary', {}, 'Source register and applicability'), table([
        ['Basis', (s) => badge(s.source_type, 'info')],
        ['Source', (s) => s.source_url ? h('a', { href: s.source_url, target: '_blank', rel: 'noopener noreferrer' }, s.title) : s.title],
        ['Version / clause', (s) => `${s.source_version} · ${s.citation_clause}`], ['Applicability', (s) => s.applicability],
      ], sources.items)));
  };

  const auditTab = async (box) => {
    const filters = { table_name: '', action: '', row_pk: '', offset: 0 };
    const results = h('div');
    const changed = (r) => {
      const a = r.old_data || {}, b = r.new_data || {};
      const keys = [...new Set([...Object.keys(a), ...Object.keys(b)])].filter((k) => JSON.stringify(a[k]) !== JSON.stringify(b[k]));
      return keys.slice(0, 6).map((k) => h('div', { class: 'small' }, h('code', {}, k), ': ', r.action === 'INSERT' ? String(b[k]) : `${JSON.stringify(a[k])} → ${r.action === 'DELETE' ? '∅' : JSON.stringify(b[k])}`));
    };
    const load = guard(async () => {
      const data = await api('GET', '/audit-log' + qs({ ...filters, limit: 25 }));
      results.replaceChildren(table([['When', (r) => fmtDT(r.occurred_at)], ['Who', (r) => r.actor_user_id ? '#' + r.actor_user_id : 'system'], ['Action', (r) => badge(r.action, 'info')],
        ['Table', (r) => r.table_name], ['Row', (r) => r.row_pk], ['Change', changed]], data.items, 'Nothing logged.'), pager(data, (o) => { filters.offset = o; load(); }));
    });
    box.append(h('p', { class: 'muted' }, 'Append-only: the database refuses UPDATE and DELETE on this table, even for its owner. Password hashes are never written here.'),
      h('div', { class: 'panel' }, form([{ name: 'table_name', label: 'Table', hint: 'e.g. entry_permit, rule_parameter' }, { name: 'row_pk', label: 'Row key' },
        { name: 'action', label: 'Action', type: 'select', options: ['INSERT', 'UPDATE', 'DELETE'].map((a) => ({ value: a, label: a })) }],
      async (v) => { Object.assign(filters, { table_name: v.table_name || '', row_pk: v.row_pk || '', action: v.action || '', offset: 0 }); await load(); }, { submit: 'Filter' })), results);
    await load();
  };

  const items = [];
  if (admin) items.push({ id: 'users', label: 'Users', render: usersTab });
  items.push({ id: 'rules', label: 'Policy and sources', render: rulesTab }, { id: 'audit', label: 'Audit log', render: auditTab });
  root.append(tabs(items));
}
