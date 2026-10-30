import React, { useEffect, useState } from 'react';
import { X, Users, ShieldAlert, HardDrive, UserPlus, KeyRound, Ban, CheckCircle2, Crown, Trash2, Pencil, Unlock, LogOut, RefreshCw } from 'lucide-react';
import { AvatarDisplay } from './AccountModal';
import { formatRelativeDate } from '../utils/animes';

const EVENTS = {
  login: 'Connexion',
  login_failed: 'Échec de connexion',
  login_refused: 'Connexion refusée',
  locked: 'Blocage anti force brute',
  unlocked: 'Déblocage',
  account_created: 'Compte créé',
  account_deleted: 'Compte supprimé',
  renamed: 'Pseudo changé',
  password_changed: 'Mot de passe changé',
  password_reset: 'Mot de passe réinitialisé',
  disabled: 'Compte désactivé',
  enabled: 'Compte réactivé',
  admin_claimed: 'Super administrateur (code)',
  admin_transferred: 'Rôle transféré',
  session_ended: 'Session fermée',
  policy_changed: 'Règles modifiées'
};

async function send(url, method = 'GET', body) {
  const res = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Erreur ${res.status}`);
  return data;
}

const when = (t) => (t ? formatRelativeDate(t) : 'Jamais');

function AccountsTab({ me, notify, onAdminLost }) {
  const [users, setUsers] = useState([]);
  const [editing, setEditing] = useState(null);   // { id, field: 'rename'|'password'|'transfer', value }
  const [creating, setCreating] = useState({ username: '', password: '' });

  const load = () => send('/api/admin/users').then(setUsers).catch((e) => notify(false, e.message));
  useEffect(() => { load(); }, []);

  const act = async (promise, text) => {
    try {
      await promise;
      notify(true, text);
      setEditing(null);
      load();
      return true;
    } catch (e) {
      notify(false, e.message);
      return false;
    }
  };

  const submitEdit = async (e, user) => {
    e.preventDefault();
    const { field, value } = editing;
    if (field === 'rename') act(send(`/api/admin/users/${user.id}`, 'PATCH', { username: value }), 'Pseudo modifié.');
    if (field === 'password') act(send(`/api/admin/users/${user.id}/password`, 'POST', { password: value }),
      `Mot de passe de ${user.username} réinitialisé : ses appareils sont déconnectés.`);
    if (field === 'transfer' && await act(send(`/api/admin/users/${user.id}/make-admin`, 'POST', { password: value }),
      `${user.username} est maintenant le super administrateur.`)) onAdminLost();
  };

  const create = async (e) => {
    e.preventDefault();
    if (await act(send('/api/admin/users', 'POST', creating), `Compte ${creating.username} créé.`)) setCreating({ username: '', password: '' });
  };

  const editor = (user, field, placeholder, type = 'text', button = 'Valider') => editing?.id === user.id && editing.field === field && (
    <form className="admin-edit" onSubmit={(e) => submitEdit(e, user)}>
      <input type={type} autoFocus required minLength={type === 'password' ? (field === 'transfer' ? 1 : 8) : 2} value={editing.value}
        placeholder={placeholder} autoComplete={type === 'password' ? 'new-password' : 'off'}
        onChange={(e) => setEditing({ ...editing, value: e.target.value })} />
      <button className="btn btn-primary">{button}</button>
      <button type="button" className="btn btn-ghost" onClick={() => setEditing(null)}>Annuler</button>
    </form>
  );

  return (
    <>
      <ul className="admin-list">
        {users.map((u) => (
          <li key={u.id} className={u.disabled ? 'is-disabled' : ''}>
            <div className="admin-user">
              <AvatarDisplay avatar={u.avatar} size={34} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <strong>{u.username}</strong>
                {u.role === 'admin' && <span className="badge badge-admin">Super admin</span>}
                {u.disabled && <span className="badge badge-off">Désactivé</span>}
                {u.id === me.id && <span className="badge">Vous</span>}
                <small>Créé {when(u.created_at).toLowerCase()} · dernière connexion : {when(u.last_login).toLowerCase()}{u.last_ip ? ` (${u.last_ip})` : ''}</small>
              </div>
            </div>
            <div className="admin-actions">
              <button className="btn btn-ghost" title="Renommer" onClick={() => setEditing({ id: u.id, field: 'rename', value: u.username })}><Pencil size={14} /></button>
              <button className="btn btn-ghost" title="Réinitialiser le mot de passe" onClick={() => setEditing({ id: u.id, field: 'password', value: '' })}><KeyRound size={14} /></button>
              {u.role !== 'admin' && (
                <>
                  <button className="btn btn-ghost" title={u.disabled ? 'Réactiver' : 'Désactiver (ses appareils sont déconnectés)'}
                    onClick={() => act(send(`/api/admin/users/${u.id}`, 'PATCH', { disabled: !u.disabled }), u.disabled ? 'Compte réactivé.' : 'Compte désactivé.')}>
                    {u.disabled ? <CheckCircle2 size={14} /> : <Ban size={14} />}
                  </button>
                  <button className="btn btn-ghost" title="Transférer le rôle de super administrateur" onClick={() => setEditing({ id: u.id, field: 'transfer', value: '' })}><Crown size={14} /></button>
                  <button className="btn btn-ghost danger" title="Supprimer le compte et ses données"
                    onClick={() => window.confirm(`Supprimer ${u.username}, son historique et sa liste ?`)
                      && act(send(`/api/admin/users/${u.id}`, 'DELETE'), `Compte ${u.username} supprimé.`)}>
                    <Trash2 size={14} />
                  </button>
                </>
              )}
            </div>
            {editor(u, 'rename', 'Nouveau pseudo')}
            {editor(u, 'password', 'Nouveau mot de passe (8 caractères min.)', 'password', 'Réinitialiser')}
            {editor(u, 'transfer', 'Votre mot de passe pour confirmer', 'password', `Donner le rôle à ${u.username}`)}
          </li>
        ))}
      </ul>

      <form className="admin-create" onSubmit={create}>
        <h4><UserPlus size={15} /> Créer un compte</h4>
        <input placeholder="Pseudo" required minLength={2} maxLength={32} autoComplete="off" value={creating.username}
          onChange={(e) => setCreating({ ...creating, username: e.target.value })} />
        <input type="password" placeholder="Mot de passe (8 caractères min.)" required minLength={8} autoComplete="new-password" value={creating.password}
          onChange={(e) => setCreating({ ...creating, password: e.target.value })} />
        <button className="btn btn-primary">Créer</button>
      </form>
    </>
  );
}

function SecurityTab({ notify }) {
  const [data, setData] = useState(null);
  const load = () => send('/api/admin/security').then(setData).catch((e) => notify(false, e.message));
  useEffect(() => { load(); }, []);

  const act = (promise, text) => promise.then(() => { notify(true, text); load(); }).catch((e) => notify(false, e.message));

  if (!data) return <p className="admin-empty">Chargement…</p>;
  return (
    <>
      <h4 className="admin-sub"><Unlock size={15} /> Blocages en cours</h4>
      {data.lockouts.length === 0 ? <p className="admin-empty">Aucun : personne n'est bloqué.</p> : (
        <ul className="admin-list compact">
          {data.lockouts.map((l) => (
            <li key={l.key}>
              <span style={{ flex: 1 }}>
                <strong>{l.kind === 'ip' ? `Adresse ${l.value}` : `Compte « ${l.value} »`}</strong>
                <small>jusqu'à {new Date(l.until * 1000).toLocaleTimeString()} · {l.count} blocage(s)</small>
              </span>
              <button className="btn btn-ghost" onClick={() => act(send(`/api/admin/lockouts/${encodeURIComponent(l.key)}`, 'DELETE'), 'Débloqué.')}>Débloquer</button>
            </li>
          ))}
        </ul>
      )}

      <h4 className="admin-sub"><LogOut size={15} /> Sessions ouvertes</h4>
      <ul className="admin-list compact">
        {data.sessions.map((s) => (
          <li key={s.id}>
            <span style={{ flex: 1, minWidth: 0 }}>
              <strong>{s.username}</strong>{s.current && <span className="badge">Vous, ici</span>}
              <small>{s.ip} · {s.agent.slice(0, 60)} · active {formatRelativeDate(s.last_seen).toLowerCase()}</small>
            </span>
            {!s.current && <button className="btn btn-ghost" onClick={() => act(send(`/api/admin/sessions/${s.id}`, 'DELETE'), 'Session fermée.')}>Fermer</button>}
          </li>
        ))}
      </ul>

      <h4 className="admin-sub"><ShieldAlert size={15} /> Journal de sécurité <button className="btn btn-ghost" onClick={load} title="Actualiser"><RefreshCw size={13} /></button></h4>
      <ul className="admin-log">
        {data.events.map((e, i) => (
          <li key={i} className={`log-${e.event}`}>
            <time>{new Date(e.at * 1000).toLocaleString()}</time>
            <span>{EVENTS[e.event] || e.event}</span>
            <span>{e.username}{e.by ? ` (par ${e.by})` : ''}</span>
            <span className="log-meta">{[e.ip, e.detail].filter(Boolean).join(' · ')}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function DownloadsTab({ notify }) {
  const [policy, setPolicy] = useState(null);
  useEffect(() => { send('/api/admin/policy').then(setPolicy).catch((e) => notify(false, e.message)); }, []);

  const save = (changes) => send('/api/admin/policy', 'POST', changes)
    .then((p) => { setPolicy(p); notify(true, 'Règles enregistrées.'); })
    .catch((e) => notify(false, e.message));

  if (!policy) return <p className="admin-empty">Chargement…</p>;
  const number = (key, label, help, props) => (
    <label className="admin-field">
      <span>{label}<small>{help}</small></span>
      <input type="number" defaultValue={policy[key]} {...props}
        onBlur={(e) => Number(e.target.value) !== policy[key] && save({ [key]: Number(e.target.value) })} />
    </label>
  );

  return (
    <>
      <label className="admin-switch">
        <input type="checkbox" checked={policy.registration_open} onChange={(e) => save({ registration_open: e.target.checked })} />
        <span>Création de compte ouverte<small>Fermée : seuls les comptes que vous créez peuvent se connecter.</small></span>
      </label>
      <label className="admin-switch">
        <input type="checkbox" checked={policy.server_downloads} onChange={(e) => save({ server_downloads: e.target.checked })} />
        <span>Téléchargement sur le serveur
          <small>Désactivé : les utilisateurs n'enregistrent les épisodes que sur leur propre appareil (vous gardez l'accès).</small>
        </span>
      </label>
      {number('min_free_gb', 'Espace disque à garder libre (Go)',
        `Aucun téléchargement en dessous${policy.disk_free_gb != null ? ` · ${policy.disk_free_gb} Go libres actuellement` : ''}.`,
        { min: 0, max: 10000, step: 1 })}
      {number('device_max_episodes', 'Épisodes par demande « Sur cet appareil »', 'Au-delà, la demande est refusée.', { min: 1, max: 500 })}
      {number('device_max_active', 'Épisodes en préparation par utilisateur', 'Ils passent par le disque du serveur avant la copie.', { min: 1, max: 200 })}
    </>
  );
}

const TABS = [
  { key: 'accounts', label: 'Comptes', icon: <Users size={15} /> },
  { key: 'security', label: 'Sécurité', icon: <ShieldAlert size={15} /> },
  { key: 'downloads', label: 'Inscriptions & téléchargements', icon: <HardDrive size={15} /> }
];

export default function AdminModal({ isOpen, onClose, currentUser, onAdminLost }) {
  const [tab, setTab] = useState('accounts');
  const [message, setMessage] = useState(null);
  useEffect(() => { if (isOpen) setMessage(null); }, [isOpen, tab]);
  if (!isOpen) return null;
  const notify = (ok, text) => setMessage({ ok, text });

  return (
    <div className="modal-overlay account-overlay" onClick={onClose}>
      <div className="surface animate-fade-in modal-sheet admin-sheet" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Administration">
        <div className="account-head">
          <ShieldAlert size={22} color="var(--yt-red)" />
          <h2 style={{ flex: 1 }}>Administration</h2>
          <button className="btn btn-icon btn-secondary" onClick={onClose} aria-label="Fermer"><X size={18} /></button>
        </div>
        <div className="login-tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t.key} role="tab" aria-selected={tab === t.key} className={`chip${tab === t.key ? ' active' : ''}`} onClick={() => setTab(t.key)}>
              {t.icon} {t.label}
            </button>
          ))}
        </div>
        {message && <p className={`account-message ${message.ok ? 'ok' : 'error'}`} role="status">{message.text}</p>}
        <div className="admin-body">
          {tab === 'accounts' && <AccountsTab me={currentUser} notify={notify} onAdminLost={onAdminLost} />}
          {tab === 'security' && <SecurityTab notify={notify} />}
          {tab === 'downloads' && <DownloadsTab notify={notify} />}
        </div>
      </div>
    </div>
  );
}
