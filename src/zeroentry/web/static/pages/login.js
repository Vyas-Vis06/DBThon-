import { api, form, h } from '/static/app.js';

export default async function (root) {
  root.append(h('div', { class: 'panel login' },
    h('h1', {}, 'Sign in'),
    h('p', { class: 'muted' }, 'Entry to a sewer is denied unless the database can prove every safeguard. Sign in to continue.'),
    form([
      { name: 'email', label: 'Email', type: 'email', required: true, attrs: { autocomplete: 'username' } },
      { name: 'password', label: 'Password', type: 'password', required: true, attrs: { autocomplete: 'current-password' } },
    ], async (values) => {
      await api('POST', '/auth/login', values);
      location.assign('/app/dashboard');
    }, { submit: 'Sign in' }),
    h('p', { class: 'small muted' }, 'Repeated failures lock the account for a few minutes.')));
}
