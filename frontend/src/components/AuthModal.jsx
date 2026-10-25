import React, { useState, useEffect } from 'react';
import { User, UserPlus, LogIn, Check, X, Shield, Sparkles } from 'lucide-react';

const AVATARS = ['👤', '🦊', '🐉', '⚡', '🔥', '🌊', '⚔️', '🎭', '👑', '🍥'];

export default function AuthModal({ isOpen, onClose, currentUser, onSelectUser }) {
  const [users, setUsers] = useState([]);
  const [activeTab, setActiveTab] = useState('select'); // 'select' or 'register'
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [selectedAvatar, setSelectedAvatar] = useState('👤');
  const [errorMsg, setErrorMsg] = useState('');

  const fetchUsers = () => {
    fetch('/api/users')
      .then((res) => res.json())
      .then((data) => setUsers(data || []))
      .catch((err) => console.error("Error fetching users:", err));
  };

  useEffect(() => {
    if (isOpen) {
      fetchUsers();
      setErrorMsg('');
    }
  }, [isOpen]);

  const handleRegister = (e) => {
    e.preventDefault();
    if (!newUsername.trim()) {
      setErrorMsg("Veuillez entrer un nom d'utilisateur.");
      return;
    }

    fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: newUsername.trim(),
        password: newPassword,
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
        onClose();
      })
      .catch((err) => setErrorMsg(err.message));
  };

  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 70,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px',
      background: 'rgba(0, 0, 0, 0.8)',
      backdropFilter: 'blur(8px)'
    }} onClick={onClose}>
      <div
        className="surface animate-fade-in"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '460px',
          borderRadius: 'var(--radius-md)',
          padding: '24px',
          boxShadow: '0 8px 32px rgba(0,0,0,0.6)'
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={18} color="var(--primary)" />
            <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#fff' }}>Compte & Profils Nami</h3>
          </div>
          {currentUser && (
            <button className="btn btn-icon btn-secondary" onClick={onClose}>
              <X size={16} />
            </button>
          )}
        </div>

        {/* Tab Selection */}
        <div style={{ display: 'flex', gap: '4px', background: '#0D1117', padding: '4px', borderRadius: 'var(--radius-sm)', marginBottom: '18px', border: '1px solid var(--border-color)' }}>
          <button
            style={{
              flex: 1,
              padding: '6px',
              fontSize: '0.82rem',
              fontWeight: 600,
              borderRadius: 'var(--radius-sm)',
              border: 'none',
              background: activeTab === 'select' ? '#21262D' : 'transparent',
              color: activeTab === 'select' ? '#fff' : 'var(--text-muted)',
              cursor: 'pointer'
            }}
            onClick={() => setActiveTab('select')}
          >
            Choisir un profil
          </button>
          <button
            style={{
              flex: 1,
              padding: '6px',
              fontSize: '0.82rem',
              fontWeight: 600,
              borderRadius: 'var(--radius-sm)',
              border: 'none',
              background: activeTab === 'register' ? '#21262D' : 'transparent',
              color: activeTab === 'register' ? '#fff' : 'var(--text-muted)',
              cursor: 'pointer'
            }}
            onClick={() => setActiveTab('register')}
          >
            Nouveau profil
          </button>
        </div>

        {errorMsg && (
          <div style={{ padding: '8px 12px', background: 'rgba(255, 107, 107, 0.1)', border: '1px solid var(--primary)', borderRadius: 'var(--radius-sm)', color: 'var(--primary)', fontSize: '0.8rem', marginBottom: '14px' }}>
            {errorMsg}
          </div>
        )}

        {activeTab === 'select' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '280px', overflowY: 'auto' }}>
            {users.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>Aucun profil existant.</p>
            ) : (
              users.map((user) => {
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
                      onSelectUser(user);
                      onClose();
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <span style={{ fontSize: '1.4rem' }}>{user.avatar || '👤'}</span>
                      <div>
                        <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#fff' }}>{user.username}</h4>
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>ID: {user.id}</span>
                      </div>
                    </div>

                    {isSelected && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.75rem', color: 'var(--accent-cyan)', fontWeight: 600 }}>
                        <Check size={14} /> Actif
                      </span>
                    )}
                  </div>
                );
              })
            )}
          </div>
        ) : (
          <form onSubmit={handleRegister} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '6px', color: '#fff' }}>
                Choisir un avatar
              </label>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {AVATARS.map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    style={{
                      width: '36px',
                      height: '36px',
                      borderRadius: 'var(--radius-sm)',
                      border: selectedAvatar === emoji ? '2px solid var(--accent-cyan)' : '1px solid var(--border-color)',
                      background: selectedAvatar === emoji ? '#21262D' : '#0D1117',
                      fontSize: '1.2rem',
                      cursor: 'pointer'
                    }}
                    onClick={() => setSelectedAvatar(emoji)}
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: '4px', color: '#fff' }}>
                Nom du profil
              </label>
              <input
                type="text"
                placeholder="Ex: Alex, Naruto, Samira..."
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  background: '#0D1117',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-sm)',
                  color: '#fff',
                  fontSize: '0.88rem',
                  outline: 'none'
                }}
              />
            </div>

            <button type="submit" className="btn btn-primary" style={{ padding: '10px', marginTop: '6px', fontSize: '0.88rem' }}>
              <UserPlus size={15} /> Créer le profil
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
