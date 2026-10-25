import React, { useState, useEffect, useRef } from 'react';
import { User, UserPlus, LogIn, Check, X, Shield, Sparkles, KeyRound, Camera, Upload, Image, Trash2, AlertTriangle } from 'lucide-react';

const AVATARS = ['👤', '🦊', '🐉', '⚡', '🔥', '🌊', '⚔️', '🎭', '👑', '🍥', '🐱', '🌸'];

// Helper to check if an avatar is a data URI (custom image) vs emoji
const isDataUri = (avatar) => avatar && avatar.startsWith('data:');

// Renders avatar as either an image or emoji span
function AvatarDisplay({ avatar, size = 36 }) {
  if (isDataUri(avatar)) {
    return (
      <img
        src={avatar}
        alt="Avatar"
        style={{
          width: `${size}px`,
          height: `${size}px`,
          borderRadius: '50%',
          objectFit: 'cover',
          border: '2px solid var(--border-color)',
          flexShrink: 0
        }}
      />
    );
  }
  return <span style={{ fontSize: `${size * 0.7}px`, lineHeight: 1 }}>{avatar || '👤'}</span>;
}

export default function AuthModal({ isOpen, onClose, currentUser, onSelectUser }) {
  const [users, setUsers] = useState([]);
  const [activeTab, setActiveTab] = useState('register'); // 'select' or 'register'
  const [selectedUserForLogin, setSelectedUserForLogin] = useState(null);
  const [loginPassword, setLoginPassword] = useState('');

  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [selectedAvatar, setSelectedAvatar] = useState('👤');
  const [errorMsg, setErrorMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // User deletion state
  const [userToDelete, setUserToDelete] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Profile picture upload
  const fileInputRef = useRef(null);
  const [avatarPreview, setAvatarPreview] = useState(null); // data URI preview for new profile
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);

  const handleDeleteUser = async (user) => {
    if (!user) return;
    setIsDeleting(true);
    setErrorMsg('');
    try {
      const res = await fetch(`/api/users/${user.id}`, {
        method: 'DELETE'
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Erreur lors de la suppression de l'utilisateur.");
      }
      if (currentUser?.id === user.id) {
        onSelectUser(null);
      }
      setUserToDelete(null);
      setSelectedUserForLogin(null);
      fetchUsers();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setIsDeleting(false);
    }
  };

  const fetchUsers = () => {
    fetch('/api/users')
      .then((res) => res.json())
      .then((data) => {
        const uList = data || [];
        setUsers(uList);
        if (uList.length === 0) {
          setActiveTab('register');
        } else if (!currentUser) {
          setActiveTab('select');
        }
      })
      .catch((err) => console.error("Error fetching users:", err));
  };

  useEffect(() => {
    if (isOpen) {
      fetchUsers();
      setErrorMsg('');
      setSelectedUserForLogin(null);
      setLoginPassword('');
      setAvatarPreview(null);
    }
  }, [isOpen]);

  // Handle file selection for custom avatar
  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      setErrorMsg("L'image ne doit pas dépasser 2 Mo.");
      return;
    }
    const reader = new FileReader();
    reader.onload = (ev) => {
      setAvatarPreview(ev.target.result);
      setSelectedAvatar(ev.target.result); // Use data URI as avatar
    };
    reader.readAsDataURL(file);
  };

  // Upload avatar for an existing user
  const handleUploadAvatarForUser = async (file) => {
    if (!currentUser) return;
    if (file.size > 2 * 1024 * 1024) {
      setErrorMsg("L'image ne doit pas dépasser 2 Mo.");
      return;
    }
    setIsUploadingAvatar(true);
    setErrorMsg('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch('/api/auth/avatar', {
        method: 'POST',
        headers: { 'X-User-ID': currentUser.id },
        body: formData
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Erreur lors de l'upload.");
      }
      const updatedUser = await res.json();
      onSelectUser(updatedUser);
      fetchUsers();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setIsUploadingAvatar(false);
    }
  };

  // Change avatar to emoji for existing user
  const handleChangeEmojiAvatar = async (emoji) => {
    if (!currentUser) return;
    try {
      const res = await fetch('/api/auth/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-User-ID': currentUser.id },
        body: JSON.stringify({ avatar: emoji })
      });
      if (res.ok) {
        const updatedUser = await res.json();
        onSelectUser(updatedUser);
        fetchUsers();
      }
    } catch (err) {
      console.error("Error updating avatar:", err);
    }
  };

  const handleRegister = (e) => {
    e.preventDefault();
    setErrorMsg('');
    const u = newUsername.trim();
    const p = newPassword.trim();
    if (!u) {
      setErrorMsg("Veuillez entrer un nom d'utilisateur.");
      return;
    }
    if (!p) {
      setErrorMsg("Veuillez entrer un mot de passe sécurisé.");
      return;
    }

    setIsLoading(true);
    fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: u,
        password: p,
        avatar: selectedAvatar
      })
    })
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Erreur lors de la création du compte.");
        }
        return res.json();
      })
      .then((user) => {
        onSelectUser(user);
        setNewUsername('');
        setNewPassword('');
        setAvatarPreview(null);
        onClose();
      })
      .catch((err) => setErrorMsg(err.message))
      .finally(() => setIsLoading(false));
  };

  const handleLogin = (e) => {
    e.preventDefault();
    if (!selectedUserForLogin) return;
    setErrorMsg('');
    setIsLoading(true);

    fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: selectedUserForLogin.username,
        password: loginPassword
      })
    })
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Mot de passe incorrect.");
        }
        return res.json();
      })
      .then((user) => {
        onSelectUser(user);
        setSelectedUserForLogin(null);
        setLoginPassword('');
        onClose();
      })
      .catch((err) => setErrorMsg(err.message))
      .finally(() => setIsLoading(false));
  };

  if (!isOpen) return null;

  const isMandatory = users.length === 0 || !currentUser;

  return (
    <div className="modal-overlay" style={{
      position: 'fixed',
      inset: 0,
      zIndex: 70,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px',
      background: 'rgba(0, 0, 0, 0.85)',
      backdropFilter: 'blur(8px)'
    }} onClick={() => { if (!isMandatory) onClose(); }}>
      <div
        className="surface animate-fade-in modal-sheet"
        onClick={(e) => e.stopPropagation()}
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: '480px',
          maxHeight: '90vh',
          overflowY: 'auto',
          borderRadius: 'var(--radius-md)',
          padding: '24px',
          boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-color)'
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={18} color="var(--primary)" />
            <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#fff' }}>
              {users.length === 0 ? "Création du premier utilisateur" : "Compte & Profils"}
            </h3>
          </div>
          {!isMandatory && (
            <button className="btn btn-icon btn-secondary" onClick={onClose}>
              <X size={16} />
            </button>
          )}
        </div>

        {/* Tab Selection if users exist */}
        {users.length > 0 && (
          <div style={{ display: 'flex', gap: '4px', background: '#0F0F0F', padding: '4px', borderRadius: 'var(--radius-sm)', marginBottom: '18px', border: '1px solid var(--border-color)' }}>
            <button
              style={{
                flex: 1,
                padding: '6px',
                fontSize: '0.82rem',
                fontWeight: 600,
                borderRadius: 'var(--radius-sm)',
                border: 'none',
                background: activeTab === 'select' ? '#272727' : 'transparent',
                color: activeTab === 'select' ? '#fff' : 'var(--text-muted)',
                cursor: 'pointer'
              }}
              onClick={() => { setActiveTab('select'); setSelectedUserForLogin(null); setErrorMsg(''); }}
            >
              Connexion / Profils
            </button>
            <button
              style={{
                flex: 1,
                padding: '6px',
                fontSize: '0.82rem',
                fontWeight: 600,
                borderRadius: 'var(--radius-sm)',
                border: 'none',
                background: activeTab === 'register' ? '#272727' : 'transparent',
                color: activeTab === 'register' ? '#fff' : 'var(--text-muted)',
                cursor: 'pointer'
              }}
              onClick={() => { setActiveTab('register'); setErrorMsg(''); }}
            >
              Nouveau profil
            </button>
          </div>
        )}

        {errorMsg && (
          <div style={{ padding: '8px 12px', background: 'rgba(255, 107, 107, 0.1)', border: '1px solid var(--primary)', borderRadius: 'var(--radius-sm)', color: 'var(--primary)', fontSize: '0.8rem', marginBottom: '14px' }}>
            {errorMsg}
          </div>
        )}

        {activeTab === 'select' && users.length > 0 ? (
          <div>
            {!selectedUserForLogin ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '280px', overflowY: 'auto' }}>
                {users.map((user) => {
                  const isSelected = currentUser?.id === user.id;
                  return (
                    <div
                      key={user.id}
                      className="surface-card"
                      style={{
                        padding: '12px 16px',
                        borderRadius: 'var(--radius-sm)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        cursor: 'pointer',
                        border: isSelected ? '1px solid var(--accent-cyan)' : '1px solid var(--border-color)',
                        background: isSelected ? 'rgba(0, 180, 216, 0.08)' : 'var(--bg-card)'
                      }}
                      onClick={() => {
                        setSelectedUserForLogin(user);
                        setLoginPassword('');
                        setErrorMsg('');
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <AvatarDisplay avatar={user.avatar} size={36} />
                        <div>
                          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#fff' }}>{user.username}</h4>
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Cliquer pour se connecter</span>
                        </div>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {isSelected && (
                          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.75rem', color: 'var(--accent-cyan)', fontWeight: 600 }}>
                            <Check size={14} /> Actif
                          </span>
                        )}
                        <button
                          type="button"
                          className="btn btn-icon"
                          style={{
                            color: 'var(--text-dim)',
                            background: 'transparent',
                            border: 'none',
                            padding: '6px',
                            cursor: 'pointer',
                            borderRadius: 'var(--radius-sm)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            transition: 'color 0.2s'
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.color = '#F85149'; }}
                          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-dim)'; }}
                          title={`Supprimer le compte de ${user.username}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            setUserToDelete(user);
                          }}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '10px', background: '#0F0F0F', borderRadius: 'var(--radius-sm)' }}>
                  <AvatarDisplay avatar={selectedUserForLogin.avatar} size={40} />
                  <div>
                    <h4 style={{ color: '#fff', fontWeight: 700 }}>{selectedUserForLogin.username}</h4>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Entrez votre mot de passe</span>
                  </div>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '6px', color: '#fff' }}>
                    Mot de passe
                  </label>
                  <input
                    type="password"
                    placeholder="Votre mot de passe..."
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    required
                    autoFocus
                    style={{
                      width: '100%',
                      padding: '9px 12px',
                      background: '#0F0F0F',
                      border: '1px solid var(--border-color)',
                      borderRadius: 'var(--radius-sm)',
                      color: '#fff',
                      fontSize: '0.88rem',
                      outline: 'none'
                    }}
                  />
                </div>

                <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ flex: 1 }}
                    onClick={() => setSelectedUserForLogin(null)}
                  >
                    Retour
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    style={{ flex: 2 }}
                    disabled={isLoading}
                  >
                    <LogIn size={15} /> Se connecter
                  </button>
                </div>
              </form>
            )}

            {/* Current user profile customization section */}
            {currentUser && !selectedUserForLogin && (
              <div style={{ marginTop: '18px', paddingTop: '18px', borderTop: '1px solid var(--border-color)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                  <Camera size={15} color="var(--accent-cyan)" />
                  <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#fff' }}>Personnaliser le profil</h4>
                </div>

                {/* Current avatar display */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '14px' }}>
                  <div style={{ position: 'relative' }}>
                    <AvatarDisplay avatar={currentUser.avatar} size={56} />
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      style={{
                        position: 'absolute',
                        bottom: '-4px',
                        right: '-4px',
                        width: '24px',
                        height: '24px',
                        borderRadius: '50%',
                        background: 'var(--primary)',
                        border: '2px solid var(--bg-surface)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        cursor: 'pointer',
                        padding: 0
                      }}
                      title="Changer la photo de profil"
                    >
                      <Camera size={11} color="#fff" />
                    </button>
                  </div>
                  <div>
                    <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#fff' }}>{currentUser.username}</h4>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {isDataUri(currentUser.avatar) ? 'Photo personnalisée' : 'Avatar emoji'}
                    </span>
                  </div>
                </div>

                {/* Hidden file input */}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleUploadAvatarForUser(file);
                    e.target.value = '';
                  }}
                  style={{ display: 'none' }}
                />

                {/* Upload button */}
                <button
                  className="btn btn-secondary"
                  style={{ width: '100%', fontSize: '0.8rem', padding: '7px 12px', marginBottom: '10px' }}
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploadingAvatar}
                >
                  {isUploadingAvatar ? (
                    <><span className="animate-spin" style={{ display: 'inline-block' }}>⏳</span> Upload en cours...</>
                  ) : (
                    <><Upload size={13} /> Importer une photo de profil (max 2 Mo)</>
                  )}
                </button>

                {/* Emoji selector for quick change */}
                <div>
                  <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 600, marginBottom: '6px', color: 'var(--text-muted)' }}>
                    Ou choisir un emoji :
                  </label>
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {AVATARS.map((emoji) => (
                      <button
                        key={emoji}
                        type="button"
                        style={{
                          width: '34px',
                          height: '34px',
                          borderRadius: 'var(--radius-sm)',
                          border: currentUser.avatar === emoji ? '2px solid var(--accent-cyan)' : '1px solid var(--border-color)',
                          background: currentUser.avatar === emoji ? '#272727' : '#0F0F0F',
                          fontSize: '1.1rem',
                          cursor: 'pointer'
                        }}
                        onClick={() => handleChangeEmojiAvatar(emoji)}
                      >
                        {emoji}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Danger zone to delete current user */}
                <div style={{ marginTop: '18px', paddingTop: '14px', borderTop: '1px solid rgba(248, 81, 73, 0.2)' }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{
                      width: '100%',
                      color: '#F85149',
                      borderColor: 'rgba(248, 81, 73, 0.3)',
                      background: 'rgba(248, 81, 73, 0.08)',
                      fontSize: '0.8rem',
                      padding: '8px 12px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '8px'
                    }}
                    onClick={() => setUserToDelete(currentUser)}
                  >
                    <Trash2 size={14} /> Supprimer ce compte et toutes ses données
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <form onSubmit={handleRegister} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {users.length === 0 && (
              <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>
                Aucun utilisateur n'est configuré. Veuillez créer le compte initial avec un nom d'utilisateur et un mot de passe.
              </p>
            )}

            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '6px', color: '#fff' }}>
                Avatar
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                {/* Preview */}
                <div style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '50%',
                  background: '#0F0F0F',
                  border: '2px solid var(--accent-cyan)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  overflow: 'hidden',
                  flexShrink: 0
                }}>
                  {avatarPreview ? (
                    <img src={avatarPreview} alt="Preview" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  ) : (
                    <span style={{ fontSize: '1.5rem' }}>{selectedAvatar}</span>
                  )}
                </div>

                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ fontSize: '0.78rem', padding: '5px 10px' }}
                  onClick={() => {
                    const input = document.createElement('input');
                    input.type = 'file';
                    input.accept = 'image/*';
                    input.onchange = handleFileSelect;
                    input.click();
                  }}
                >
                  <Upload size={12} /> Photo personnalisée
                </button>
              </div>

              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {AVATARS.map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    style={{
                      width: '36px',
                      height: '36px',
                      borderRadius: 'var(--radius-sm)',
                      border: (!avatarPreview && selectedAvatar === emoji) ? '2px solid var(--accent-cyan)' : '1px solid var(--border-color)',
                      background: (!avatarPreview && selectedAvatar === emoji) ? '#272727' : '#0F0F0F',
                      fontSize: '1.2rem',
                      cursor: 'pointer'
                    }}
                    onClick={() => {
                      setSelectedAvatar(emoji);
                      setAvatarPreview(null);
                    }}
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '4px', color: '#fff' }}>
                Nom d'utilisateur
              </label>
              <input
                type="text"
                placeholder="Ex: TMCooper, Alex..."
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                required
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  background: '#0F0F0F',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-sm)',
                  color: '#fff',
                  fontSize: '0.88rem',
                  outline: 'none'
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '4px', color: '#fff' }}>
                Mot de passe
              </label>
              <input
                type="password"
                placeholder="Mot de passe sécurisé..."
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  background: '#0F0F0F',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-sm)',
                  color: '#fff',
                  fontSize: '0.88rem',
                  outline: 'none'
                }}
              />
            </div>

            <button type="submit" className="btn btn-primary" style={{ padding: '10px', marginTop: '6px', fontSize: '0.88rem' }} disabled={isLoading}>
              <UserPlus size={15} /> Créer le profil
            </button>
          </form>
        )}

        {/* User Deletion Confirmation Modal Overlay */}
        {userToDelete && (
          <div style={{
            position: 'absolute',
            inset: 0,
            background: 'rgba(15, 15, 15, 0.95)',
            backdropFilter: 'blur(8px)',
            borderRadius: 'var(--radius-md)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            textAlign: 'center',
            zIndex: 80,
            gap: '14px'
          }}>
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '50%',
              background: 'rgba(248, 81, 73, 0.15)',
              border: '1px solid rgba(248, 81, 73, 0.4)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <AlertTriangle size={24} color="#F85149" />
            </div>

            <div>
              <h4 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#fff', marginBottom: '6px' }}>
                Supprimer le profil « {userToDelete.username} » ?
              </h4>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: 1.4, maxWidth: '340px' }}>
                Cette action est irréversible. L'ensemble des données associées (historique de lecture, progression des épisodes, animes récents) seront définitivement effacées.
              </p>
            </div>

            <div style={{ display: 'flex', gap: '10px', width: '100%', maxWidth: '320px', marginTop: '8px' }}>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ flex: 1, fontSize: '0.82rem' }}
                onClick={() => setUserToDelete(null)}
                disabled={isDeleting}
              >
                Annuler
              </button>
              <button
                type="button"
                className="btn"
                style={{
                  flex: 1,
                  background: '#DA3633',
                  color: '#fff',
                  border: 'none',
                  fontSize: '0.82rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px'
                }}
                onClick={() => handleDeleteUser(userToDelete)}
                disabled={isDeleting}
              >
                {isDeleting ? <span className="animate-spin">⏳</span> : <Trash2 size={14} />}
                {isDeleting ? "Suppression..." : "Supprimer"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
