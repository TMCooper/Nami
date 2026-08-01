import React from 'react';
import { Search, Download, Settings, Tv, Film, Layers } from 'lucide-react';

export default function Header({ 
  searchQuery, 
  setSearchQuery, 
  onSearch, 
  activeSource, 
  setActiveSource, 
  activeDownloadsCount, 
  onOpenDownloads, 
  onOpenSettings 
}) {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      onSearch();
    }
  };

  return (
    <header className="glass" style={{
      position: 'sticky',
      top: 0,
      zIndex: 40,
      padding: '14px 28px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '20px',
      borderBottom: '1px solid var(--border-color)'
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }} onClick={() => setSearchQuery('')}>
        <div style={{
          width: '42px',
          height: '42px',
          borderRadius: '12px',
          background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '1.4rem',
          boxShadow: '0 0 15px rgba(0, 240, 255, 0.3)'
        }}>
          波
        </div>
        <div>
          <h1 style={{ fontSize: '1.4rem', fontWeight: 800, letterSpacing: '-0.5px', background: 'linear-gradient(90deg, #fff, var(--primary))', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            NAMI
          </h1>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 500 }}>Anime Stream & Download</p>
        </div>
      </div>

      {/* Source Selector & Search Bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flex: 1, maxWidth: '650px' }}>
        {/* Source Pills */}
        <div style={{ display: 'flex', background: 'rgba(0,0,0,0.3)', padding: '4px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
          <button 
            className={`btn ${activeSource === 'all' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '6px 12px', fontSize: '0.82rem', borderRadius: 'var(--radius-sm)' }}
            onClick={() => setActiveSource('all')}
          >
            <Layers size={14} /> Tous
          </button>
          <button 
            className={`btn ${activeSource === 'anime_sama' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '6px 12px', fontSize: '0.82rem', borderRadius: 'var(--radius-sm)' }}
            onClick={() => setActiveSource('anime_sama')}
          >
            <Tv size={14} /> Anime Sama
          </button>
          <button 
            className={`btn ${activeSource === 'voiranime' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '6px 12px', fontSize: '0.82rem', borderRadius: 'var(--radius-sm)' }}
            onClick={() => setActiveSource('voiranime')}
          >
            <Film size={14} /> VoirAnime
          </button>
        </div>

        {/* Search Bar */}
        <div style={{ position: 'relative', flex: 1 }}>
          <Search size={18} style={{ position: 'absolute', left: '14px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Rechercher un anime (ex: Frieren, Solo Leveling)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            style={{
              width: '100%',
              padding: '10px 16px 10px 42px',
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-md)',
              color: '#fff',
              fontSize: '0.9rem',
              outline: 'none',
              transition: 'var(--transition)'
            }}
          />
        </div>
      </div>

      {/* Action Buttons */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button 
          className="btn btn-secondary" 
          onClick={onOpenDownloads}
          style={{ position: 'relative' }}
          title="Gestionnaire de Téléchargements"
        >
          <Download size={18} />
          <span>Téléchargements</span>
          {activeDownloadsCount > 0 && (
            <span style={{
              position: 'absolute',
              top: '-4px',
              right: '-4px',
              background: 'var(--accent-pink)',
              color: '#fff',
              fontSize: '0.7rem',
              fontWeight: 800,
              width: '20px',
              height: '20px',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 10px var(--accent-pink)'
            }}>
              {activeDownloadsCount}
            </span>
          )}
        </button>

        <button 
          className="btn btn-icon btn-secondary" 
          onClick={onOpenSettings}
          title="Paramètres"
        >
          <Settings size={18} />
        </button>
      </div>
    </header>
  );
}
