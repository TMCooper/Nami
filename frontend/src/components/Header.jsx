import React, { useState, useEffect } from 'react';
import { Search, Download, Settings, RefreshCw, Layers, History, BarChart3, HardDrive } from 'lucide-react';

export default function Header({ 
  searchQuery, 
  setSearchQuery, 
  onSearch, 
  activeSource, 
  setActiveSource, 
  activeTab,
  setActiveTab,
  activeDownloadsCount, 
  onOpenDownloads, 
  onOpenSettings,
  onOpenStats,
  currentUser,
  onOpenAuth
}) {
  const [catalogStatus, setCatalogStatus] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    const checkStatus = () => {
      fetch('/api/catalog/status')
        .then((res) => res.json())
        .then((data) => {
          setCatalogStatus(data);
          setIsRefreshing(Boolean(data.is_updating));
        })
        .catch(() => {});
    };

    checkStatus();
    const interval = setInterval(checkStatus, 12000);
    return () => clearInterval(interval);
  }, []);

  const handleRefreshCatalog = () => {
    setIsRefreshing(true);
    fetch(`/api/catalog/update?source=${activeSource}`, { method: 'POST' })
      .then((res) => res.json())
      .then((data) => setCatalogStatus(data))
      .catch((err) => console.error("Error launching refresh:", err));
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      onSearch();
    }
  };

  return (
    <header className="surface" style={{
      position: 'sticky',
      top: 0,
      zIndex: 40,
      padding: '12px 24px',
      borderBottom: '1px solid var(--border-color)',
      display: 'flex',
      flexDirection: 'column',
      gap: '12px',
      background: 'rgba(22, 27, 34, 0.85)',
      backdropFilter: 'blur(12px)'
    }}>
      {/* Top Row: Logo, Search, Controls */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
        {/* Logo */}
        <div 
          style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}
          onClick={() => {
            setSearchQuery('');
            setActiveTab('catalog');
          }}
        >
          <span style={{
            fontSize: '1.3rem',
            fontWeight: 900,
            letterSpacing: '1.5px',
            background: 'linear-gradient(135deg, #58A6FF, #BC8CFF)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent'
          }}>
            NAMI
          </span>
          <span style={{
            fontSize: '0.68rem',
            background: 'rgba(255,255,255,0.08)',
            color: 'var(--text-muted)',
            padding: '2px 6px',
            borderRadius: '4px',
            fontWeight: 600
          }}>
            Self-Host
          </span>
        </div>

        {/* Search Bar */}
        <div style={{ position: 'relative', flex: 1, minWidth: '220px', maxWidth: '480px' }}>
          <Search size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Rechercher un anime (Frieren, Solo Leveling...)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            style={{
              width: '100%',
              padding: '7px 14px 7px 34px',
              background: '#0D1117',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-sm)',
              color: '#fff',
              fontSize: '0.85rem',
              outline: 'none',
              transition: 'var(--transition)'
            }}
          />
        </div>

        {/* Top Right Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          {/* User Account / Profile Button */}
          <button
            className="btn btn-secondary"
            onClick={onOpenAuth}
            style={{ fontSize: '0.78rem', padding: '5px 10px', gap: '6px' }}
            title="Changer de profil ou se connecter"
          >
            <span style={{ fontSize: '1rem' }}>{currentUser?.avatar || '👤'}</span>
            <span style={{ fontWeight: 700, color: '#fff' }}>{currentUser?.username || 'Utilisateur'}</span>
          </button>

          {/* Stats Button */}
          <button
            className="btn btn-secondary"
            onClick={onOpenStats}
            style={{ fontSize: '0.78rem', padding: '5px 10px', gap: '5px' }}
            title="Voir mes statistiques de visionnage"
          >
            <BarChart3 size={13} color="var(--primary)" />
            <span>Stats</span>
          </button>

          {/* Refresh Catalog Button */}
          <button
            className="btn btn-secondary"
            onClick={handleRefreshCatalog}
            disabled={isRefreshing}
            style={{ fontSize: '0.78rem', padding: '5px 10px' }}
            title="Mettre à jour le catalogue depuis les sources"
          >
            <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />
            <span>{isRefreshing ? 'Mise à jour...' : 'Actualiser DB'}</span>
          </button>

          {/* Downloads Drawer Button */}
          <button
            className="btn btn-secondary"
            onClick={onOpenDownloads}
            style={{ position: 'relative', fontSize: '0.78rem', padding: '5px 10px' }}
          >
            <Download size={13} />
            <span>Téléchargements</span>
            {activeDownloadsCount > 0 && (
              <span style={{
                background: 'var(--primary)',
                color: '#fff',
                fontSize: '0.68rem',
                fontWeight: 800,
                padding: '1px 5px',
                borderRadius: 'var(--radius-full)',
                marginLeft: '4px'
              }}>
                {activeDownloadsCount}
              </span>
            )}
          </button>

          {/* Settings Button */}
          <button className="btn btn-icon btn-secondary" onClick={onOpenSettings} title="Paramètres" style={{ width: '30px', height: '30px' }}>
            <Settings size={14} />
          </button>
        </div>
      </div>

      {/* Bottom Row: Navigation Tabs & Source Selector */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '4px', borderTop: '1px solid rgba(255,255,255,0.04)', flexWrap: 'wrap', gap: '8px' }}>
        {/* Nav Tabs */}
        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            className={`btn ${activeTab === 'catalog' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '4px 12px', fontSize: '0.8rem' }}
            onClick={() => setActiveTab('catalog')}
          >
            <Layers size={13} /> Accueil & Catalogue
          </button>

          <button
            className={`btn ${activeTab === 'history' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '4px 12px', fontSize: '0.8rem' }}
            onClick={() => setActiveTab('history')}
          >
            <History size={13} /> Historique & Reprise
          </button>

          <button
            className={`btn ${activeTab === 'offline' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '4px 12px', fontSize: '0.8rem' }}
            onClick={() => setActiveTab('offline')}
          >
            <HardDrive size={13} color="#3FB950" /> Hors-Ligne (Disque)
          </button>
        </div>

        {/* Source Filter (Only applicable when browsing catalog) */}
        {activeTab === 'catalog' && (
          <div style={{ display: 'flex', gap: '2px', background: '#0D1117', padding: '2px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
            <button
              style={{
                padding: '3px 9px',
                fontSize: '0.73rem',
                fontWeight: 600,
                borderRadius: 'var(--radius-sm)',
                border: 'none',
                background: activeSource === 'all' ? '#21262D' : 'transparent',
                color: activeSource === 'all' ? '#fff' : 'var(--text-muted)',
                cursor: 'pointer'
              }}
              onClick={() => setActiveSource('all')}
            >
              Tous
            </button>
            <button
              style={{
                padding: '3px 9px',
                fontSize: '0.73rem',
                fontWeight: 600,
                borderRadius: 'var(--radius-sm)',
                border: 'none',
                background: activeSource === 'anime_sama' ? '#21262D' : 'transparent',
                color: activeSource === 'anime_sama' ? 'var(--accent-cyan)' : 'var(--text-muted)',
                cursor: 'pointer'
              }}
              onClick={() => setActiveSource('anime_sama')}
            >
              Anime-Sama
            </button>
            <button
              style={{
                padding: '3px 9px',
                fontSize: '0.73rem',
                fontWeight: 600,
                borderRadius: 'var(--radius-sm)',
                border: 'none',
                background: activeSource === 'voiranime' ? '#21262D' : 'transparent',
                color: activeSource === 'voiranime' ? 'var(--primary)' : 'var(--text-muted)',
                cursor: 'pointer'
              }}
              onClick={() => setActiveSource('voiranime')}
            >
              VoirAnime
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
