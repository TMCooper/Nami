import React, { useState } from 'react';
import { LogIn, UserPlus, Loader2, ShieldCheck } from 'lucide-react';

// Sign in with the pseudo and the password (no list of profiles to pick from).
// Real <form>s with autocomplete hints: the browser's password manager can save and fill them.
export default function LoginScreen({ status, onSignedIn }) {
  const canRegister = Boolean(status?.registration_open);
  const firstAccount = !status?.has_users;
  const [mode, setMode] = useState(firstAccount ? 'register' : 'login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState(status?.expired ? 'Votre session a pris fin : reconnectez-vous.' : '');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (mode === 'register' && password !== confirm) {
      setError('Les deux mots de passe ne correspondent pas.');
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(mode === 'login' ? '/api/auth/login' : '/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mode === 'login' ? { username, password, remember } : { username, password })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Erreur ${res.status}`);
      onSignedIn(data);
    } catch (err) {
      setError(err.message);
      setPassword('');
      setConfirm('');
    } finally {
      setBusy(false);
    }
  };

  const switchTo = (next) => {
    setMode(next);
    setError('');
    setPassword('');
    setConfirm('');
  };

  return (
    <div className="login-page">
      <div className="login-card surface">
        <div className="login-brand">
          <span className="login-logo">NAMI</span>
          <span className="logo-badge">Self-Host</span>
        </div>

        {!firstAccount && canRegister && (
          <div className="login-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={mode === 'login'} className={`chip${mode === 'login' ? ' active' : ''}`} onClick={() => switchTo('login')}>
              <LogIn size={14} /> Se connecter
            </button>
            <button type="button" role="tab" aria-selected={mode === 'register'} className={`chip${mode === 'register' ? ' active' : ''}`} onClick={() => switchTo('register')}>
              <UserPlus size={14} /> Créer un compte
            </button>
          </div>
        )}

        <h1 className="login-title">
          {firstAccount ? 'Bienvenue sur Nami' : mode === 'login' ? 'Connexion' : 'Nouveau compte'}
        </h1>
        {firstAccount && (
          <p className="login-hint">
            <ShieldCheck size={15} />
            <span>
              Ce premier compte sera le <strong>super administrateur</strong> : il gère les autres comptes,
              les téléchargements et les réglages du serveur.
            </span>
          </p>
        )}

        <form onSubmit={submit} className="login-form">
          <label>
            <span>Pseudo</span>
            <input
              name="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              minLength={2}
              maxLength={32}
              autoFocus
            />
          </label>
          <label>
            <span>Mot de passe</span>
            <input
              name="password"
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={mode === 'login' ? 1 : 8}
              maxLength={200}
            />
          </label>
          {mode === 'register' && (
            <>
              <label>
                <span>Confirmer le mot de passe</span>
                <input
                  name="confirm"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                  minLength={8}
                  maxLength={200}
                />
              </label>
              <p className="login-note">Au moins 8 caractères.</p>
            </>
          )}
          {mode === 'login' && (
            <label className="login-remember">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              <span>Se souvenir de moi sur cet appareil (30 jours)</span>
            </label>
          )}

          {error && <p className="login-error" role="alert">{error}</p>}

          <button type="submit" className="btn btn-primary login-submit" disabled={busy}>
            {busy ? <Loader2 className="animate-spin" size={16} /> : mode === 'login' ? <LogIn size={16} /> : <UserPlus size={16} />}
            {mode === 'login' ? 'Se connecter' : 'Créer le compte'}
          </button>
        </form>

        {!canRegister && mode === 'login' && (
          <p className="login-note">La création de compte est fermée : demandez un accès au super administrateur.</p>
        )}
      </div>
    </div>
  );
}
