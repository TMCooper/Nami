import React, { useState, useEffect } from 'react';
import { X, Clock, PlayCircle, CheckCircle, HardDrive, User, Sparkles } from 'lucide-react';

export default function StatsModal({ isOpen, onClose, currentUser }) {
  const [stats, setStats] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!isOpen) return;
    setIsLoading(true);

    fetch('/api/users/stats', {
      headers: { 'X-User-ID': currentUser?.id || 'default' }
    })
      .then((res) => res.json())
      .then((data) => setStats(data))
      .catch((err) => console.error("Error loading stats:", err))
      .finally(() => setIsLoading(false));
  }, [isOpen, currentUser]);

  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 50,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px',
      background: 'rgba(0, 0, 0, 0.85)',
      backdropFilter: 'blur(8px)'
    }} onClick={onClose}>
      <div
        className="surface animate-fade-in"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '560px',
          borderRadius: 'var(--radius-md)',
          padding: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-color)',
          position: 'relative'
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {currentUser?.avatar && (currentUser.avatar.startsWith('data:') || currentUser.avatar.startsWith('http')) ? (
              <img
                src={currentUser.avatar}
                alt="Avatar"
                style={{
                  width: '44px',
                  height: '44px',
                  borderRadius: '50%',
                  objectFit: 'cover',
                  border: '2px solid var(--accent-cyan)'
                }}
              />
            ) : (
              <span style={{ fontSize: '1.8rem' }}>{currentUser?.avatar || '📊'}</span>
            )}
            <div>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 800, margin: 0, color: '#fff' }}>Statistiques de visionnage</h3>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', margin: '2px 0 0 0' }}>Profil : {currentUser?.username || 'Utilisateur'}</p>
            </div>
          </div>
          <button className="btn btn-icon btn-secondary" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Stats Grid */}
        {isLoading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
            Calcul des statistiques...
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '14px' }}>
            {/* Watch Time */}
            <div className="surface-card" style={{ padding: '16px', borderRadius: 'var(--radius-sm)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--primary)' }}>
                <Clock size={18} />
                <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>Temps de visionnage</span>
              </div>
              <span style={{ fontSize: '1.6rem', fontWeight: 800, color: '#fff' }}>
                {stats?.watch_time_formatted || '0m'}
              </span>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>Cumul des sessions lues</span>
            </div>

            {/* Episodes Watched */}
            <div className="surface-card" style={{ padding: '16px', borderRadius: 'var(--radius-sm)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-green)' }}>
                <CheckCircle size={18} />
                <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>Épisodes terminés</span>
              </div>
              <span style={{ fontSize: '1.6rem', fontWeight: 800, color: '#fff' }}>
                {stats?.total_episodes_watched || 0}
              </span>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>Marqués comme vus</span>
            </div>

            {/* Animes Count */}
            <div className="surface-card" style={{ padding: '16px', borderRadius: 'var(--radius-sm)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-cyan)' }}>
                <PlayCircle size={18} />
                <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>Séries entamées</span>
              </div>
              <span style={{ fontSize: '1.6rem', fontWeight: 800, color: '#fff' }}>
                {stats?.total_animes_started || 0}
              </span>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                {stats?.animes_completed || 0} série(s) complétée(s)
              </span>
            </div>

            {/* Disk Storage */}
            <div className="surface-card" style={{ padding: '16px', borderRadius: 'var(--radius-sm)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#E3B341' }}>
                <HardDrive size={18} />
                <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>Stockage local utilisé</span>
              </div>
              <span style={{ fontSize: '1.6rem', fontWeight: 800, color: '#fff' }}>
                {stats?.storage_used || '0 Mo'}
              </span>
              <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>Sur le disque hôte</span>
            </div>
          </div>
        )}

        {/* Self-Host Tip */}
        <div style={{
          background: 'rgba(56, 139, 253, 0.08)',
          border: '1px solid rgba(56, 139, 253, 0.25)',
          borderRadius: 'var(--radius-sm)',
          padding: '12px 14px',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '10px'
        }}>
          <Sparkles size={16} color="var(--primary)" style={{ flexShrink: 0, marginTop: '2px' }} />
          <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>
            <strong style={{ color: '#fff' }}>Mode Self-Hosted Raspberry Pi :</strong> Les fichiers téléchargés sont conservés sur votre disque externe (hors conteneur) et streamés via Range HTTP 206 sans surcharger le processeur.
          </p>
        </div>
      </div>
    </div>
  );
}
