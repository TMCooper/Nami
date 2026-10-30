import React, { useEffect, useRef, useState } from 'react';
import { X, LogOut, KeyRound, Upload, Trash2, Monitor, ShieldCheck, Check, Loader2 } from 'lucide-react';
import { formatRelativeDate } from '../utils/animes';

const AVATARS = ['👤', '🦊', '🐉', '⚡', '🔥', '🌊', '⚔️', '🎭', '👑', '🍥', '🐱', '🌸'];

export function AvatarDisplay({ avatar, size = 36 }) {
  if (avatar && avatar.startsWith('data:')) {
    return <img src={avatar} alt="" className="avatar-img" style={{ width: size, height: size }} />;
  }
  return <span style={{ fontSize: `${size * 0.7}px`, lineHeight: 1 }}>{avatar || '👤'}</span>;
}

const browserName = (agent = '') => {
  const os = /Android/i.test(agent) ? 'Android' : /iPhone|iPad/i.test(agent) ? 'iOS' : /Windows/i.test(agent) ? 'Windows'
    : /Mac OS/i.test(agent) ? 'macOS' : /Linux/i.test(agent) ? 'Linux' : '';
  const app = /Edg\//.test(agent) ? 'Edge' : /OPR\//.test(agent) ? 'Opera' : /Firefox\//.test(agent) ? 'Firefox'
    : /Chrome\//.test(agent) ? 'Chrome' : /Safari\//.test(agent) ? 'Safari' : 'Navigateur';
  return os ? `${app} · ${os}` : app;
};

async function send(url, method, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Erreur ${res.status}`);
  return data;
}

// One's own account: profile, password, devices signed in, and the super administrator setup code
export default function AccountModal({ isOpen, onClose, currentUser, onUserChange, onSignOut, setupNeeded, onBecameAdmin }) {
  const [username, setUsername] = useState('');
  const [message, setMessage] = useState(null);   // { ok, text }
  const [passwords, setPasswords] = useState({ current: '', next: '', confirm: '' });
  const [sessions, setSessions] = useState([]);
  const [setupCode, setSetupCode] = useState('');
  const [deletePassword, setDeletePassword] = useState('');
  const [busy, setBusy] = useState('');
  const fileRef = useRef(null);

  const loadSessions = () => fetch('/api/auth/sessions').then((r) => (r.ok ? r.json() : [])).then(setSessions).catch(() => {});

  useEffect(() => {
    if (!isOpen) return;
    setUsername(currentUser?.username || '');
    setMessage(null);
    setPasswords({ current: '', next: '', confirm: '' });
    setDeletePassword('');
    loadSessions();
  }, [isOpen]);

  if (!isOpen || !currentUser) return null;

  const run = async (key, action, success) => {
    setBusy(key);
    setMessage(null);
    try {
      const result = await action();
      if (success) setMessage({ ok: true, text: typeof success === 'function' ? success(result) : success });
      return result;
    } catch (err) {
      setMessage({ ok: false, text: err.message });
      return null;
    } finally {
      setBusy('');
    }
  };

  const saveProfile = (changes) => run('profile', async () => {
    const user = await send('/api/auth/profile', 'PATCH', changes);
    onUserChange(user);
    return user;
  }, 'Profil enregistré.');

  const uploadAvatar = (file) => {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      setMessage({ ok: false, text: "L'image ne doit pas dépasser 2 Mo." });
      return;
    }
    run('avatar', async () => {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch('/api/auth/avatar', { method: 'POST', body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Erreur ${res.status}`);
      onUserChange(data);
    }, 'Photo de profil enregistrée.');
  };

  const changePassword = (e) => {
    e.preventDefault();
    if (passwords.next !== passwords.confirm) {
      setMessage({ ok: false, text: 'Les deux nouveaux mots de passe ne correspondent pas.' });
      return;
    }
    run('password', () => send('/api/auth/password', 'POST', { current_password: passwords.current, new_password: passwords.next }),
      (r) => `Mot de passe changé${r.sessions_ended ? ` : ${r.sessions_ended} autre(s) appareil(s) déconnecté(s)` : ''}.`)
      .then((r) => { if (r) { setPasswords({ current: '', next: '', confirm: '' }); loadSessions(); } });
  };

  const endSession = (id) => run(`session-${id}`, () => send(`/api/auth/sessions/${id}`, 'DELETE'), 'Appareil déconnecté.').then(loadSessions);

  const claimAdmin = (e) => {
    e.preventDefault();
    run('setup', () => send('/api/auth/setup', 'POST', { code: setupCode }), 'Vous êtes maintenant le super administrateur.')
      .then((user) => { if (user) { onUserChange(user); onBecameAdmin?.(); } });
  };

  const deleteAccount = (e) => {
    e.preventDefault();
    if (!window.confirm('Supprimer définitivement votre compte, votre historique et votre liste ? Cette action est irréversible.')) return;
    run('delete', () => send('/api/auth/delete', 'POST', { password: deletePassword })).then((r) => { if (r) onSignOut(); });
  };

  const isAdmin = currentUser.role === 'admin';

  return (
    <div className="modal-overlay account-overlay" onClick={onClose}>
      <div className="surface animate-fade-in modal-sheet account-sheet" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Mon compte">
        <div className="account-head">
          <AvatarDisplay avatar={currentUser.avatar} size={44} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2>{currentUser.username}</h2>
            <span className={`badge ${isAdmin ? 'badge-admin' : ''}`}>{isAdmin ? 'Super administrateur' : 'Utilisateur'}</span>
          </div>
          <button className="btn btn-icon btn-secondary" onClick={onClose} aria-label="Fermer"><X size={18} /></button>
        </div>

        {message && <p className={`account-message ${message.ok ? 'ok' : 'error'}`} role="status">{message.text}</p>}

        {setupNeeded && !isAdmin && (
          <section className="account-section account-setup">
            <h3><ShieldCheck size={16} /> Aucun super administrateur</h3>
            <p>
              Si ce serveur est le vôtre, saisissez le code d'installation : il se trouve dans <code>data/admin-setup.txt</code> sur
              le serveur (et dans ses journaux).
            </p>
            <form onSubmit={claimAdmin} className="account-row">
              <input value={setupCode} onChange={(e) => setSetupCode(e.target.value)} placeholder="XXXXXX-XXXXXX-XXXXXX" required autoComplete="off" />
              <button className="btn btn-primary" disabled={busy === 'setup'}>Devenir super administrateur</button>
            </form>
          </section>
        )}

        <section className="account-section">
          <h3>Profil</h3>
          <div className="avatar-picker">
            {AVATARS.map((a) => (
              <button key={a} type="button" className={`avatar-choice${currentUser.avatar === a ? ' active' : ''}`} onClick={() => saveProfile({ avatar: a })} aria-label={`Avatar ${a}`}>
                {a}
              </button>
            ))}
            <button type="button" className="avatar-choice" onClick={() => fileRef.current?.click()} title="Choisir une image" aria-label="Choisir une image">
              {busy === 'avatar' ? <Loader2 className="animate-spin" size={16} /> : <Upload size={16} />}
            </button>
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden onChange={(e) => uploadAvatar(e.target.files?.[0])} />
          </div>
          <form className="account-row" onSubmit={(e) => { e.preventDefault(); saveProfile({ username }); }}>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" minLength={2} maxLength={32} required aria-label="Pseudo" />
            <button className="btn btn-secondary" disabled={busy === 'profile' || username === currentUser.username}>
              <Check size={14} /> Renommer
            </button>
          </form>
        </section>

        <section className="account-section">
          <h3><KeyRound size={16} /> Mot de passe</h3>
          <form onSubmit={changePassword} className="account-grid">
            <input type="password" placeholder="Mot de passe actuel" autoComplete="current-password" value={passwords.current}
              onChange={(e) => setPasswords({ ...passwords, current: e.target.value })} required />
            <input type="password" placeholder="Nouveau (8 caractères min.)" autoComplete="new-password" minLength={8} value={passwords.next}
              onChange={(e) => setPasswords({ ...passwords, next: e.target.value })} required />
            <input type="password" placeholder="Confirmer le nouveau" autoComplete="new-password" minLength={8} value={passwords.confirm}
              onChange={(e) => setPasswords({ ...passwords, confirm: e.target.value })} required />
            <button className="btn btn-secondary" disabled={busy === 'password'}>Changer le mot de passe</button>
          </form>
          <p className="account-note">Les autres appareils connectés à ce compte devront se reconnecter.</p>
        </section>

        <section className="account-section">
          <h3><Monitor size={16} /> Appareils connectés</h3>
          <ul className="account-list">
            {sessions.map((s) => (
              <li key={s.id}>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <strong>{browserName(s.agent)}</strong>{s.current && <span className="badge" style={{ marginLeft: 6 }}>Cet appareil</span>}
                  <small>{s.ip} · actif {formatRelativeDate(s.last_seen).toLowerCase()}</small>
                </span>
                {!s.current && (
                  <button className="btn btn-ghost" onClick={() => endSession(s.id)} disabled={busy === `session-${s.id}`}>Déconnecter</button>
                )}
              </li>
            ))}
          </ul>
        </section>

        <div className="account-actions">
          <button className="btn btn-secondary" onClick={onSignOut}><LogOut size={15} /> Se déconnecter</button>
        </div>

        {!isAdmin && (
          <section className="account-section account-danger">
            <h3><Trash2 size={16} /> Supprimer mon compte</h3>
            <form onSubmit={deleteAccount} className="account-row">
              <input type="password" placeholder="Votre mot de passe" autoComplete="current-password" value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)} required />
              <button className="btn btn-danger" disabled={busy === 'delete'}>Supprimer</button>
            </form>
          </section>
        )}
      </div>
    </div>
  );
}
