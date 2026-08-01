import React, { useState, useEffect } from 'react';
import { Search, Download, Settings, RefreshCw, Layers, Tv, Film, History, Bookmark } from 'lucide-react';

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
  onOpenSettings 
}) {
  const [catalogStatus, setCatalogStatus] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Poll catalog update status every 3s
  useEffect(() => {
    const checkStatus = () => {
      fetch('/api/catalog/status')
        .then((res) => res.json())
        .then((data) => {
          setCatalogStatus(data);
          if (data.is_updating) {
            setIsRefreshing(true);
          } else {
            setIsRefreshing(false);
          }
        })
        .catch(() => {});
    };

    checkStatus();
    const interval = setInterval(checkStatus, 3000);
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
      gap: '12px'
    }}>
      {/* Top Row: Logo, Search, Controls */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px' }}>
        {/* Logo */}
        <div 
          style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}
          onClick={() => {
            setSearchQuery('');
            setActiveTab('catalog');
          }}
        >
          <div style={{
            width: '36px',
            height: '36px',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--primary)',
            color: '#fff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 800,
            fontSize: '1.2rem'
          }}>
            N
          </div>
          <span style={{ fontSize: '1.3rem', fontWeight: 800, letterSpacing: '-0.5px' }}>
            NAMI <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 500 }}>.anime</span>
          </span>
        </div>

        {/* Search Bar */}
        <div style={{ position: 'relative', flex: 1, maxWidth: '500px' }}>
          <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Rechercher un anime (ex: Frieren, Naruto, Solo Leveling)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            style={{
              width: '100%',
              padding: '8px 14px 8px 36px',
              background: '#0D1117',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-sm)',
              color: '#fff',
              fontSize: '0.88rem',
              outline: 'none'
            }}
          />
        </div>

        {/* Top Right Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Refresh Catalog Button */}
          <button
            className={`btn ${isRefreshing ? 'btn-secondary' : 'btn-secondary'}`}
            onClick={handleRefreshCatalog}
            disabled={isRefreshing}
            style={{ fontSize: '0.8rem', padding: '6px 12px' }}
            title="Actualiser la base de données d'animes"
          >
            <RefreshCw size={14} className={isRefreshing ? 'animate-spin' : ''} />
            <span>{isRefreshing ? 'Actualisation...' : 'Actualiser DB'}</span>
          </button>

          {/* Downloads Drawer Button */}
          <button
            className="btn btn-secondary"
            onClick={onOpenDownloads}
            style={{ position: 'relative', fontSize: '0.8rem', padding: '6px 12px' }}
          >
            <Download size={14} />
            <span>Téléchargements</span>
            {activeDownloadsCount > 0 && (
              <span style={{
                background: 'var(--primary)',
                color: '#fff',
                fontSize: '0.7rem',
                fontWeight: 800,
                padding: '1px 6px',
                borderRadius: 'var(--radius-full)',
                marginLeft: '4px'
              }}>
                {activeDownloadsCount}
              </span>
            )}
          </button>

          {/* Settings Button */}
          <button className="btn btn-icon btn-secondary" onClick={onOpenSettings} title="Paramètres">
            <Settings size={16} />
          </button>
        </div>
      </div>

      {/* Bottom Row: Navigation Tabs & Source Selector */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '4px', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
        {/* Nav Tabs */}
        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            className={`btn ${activeTab === 'catalog' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '6px 14px', fontSize: '0.82rem' }}
            onClick={() => setActiveTab('catalog')}
          >
            <Layers size={14} /> Catalogue
          </button>

          <button
            className={`btn ${activeTab === 'history' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '6px 14px', fontSize: '0.82rem' }}
            onClick={() => setActiveTab('history')}
          >
            <History size={14} /> Historique & Reprise
          </button>
        </div>

        {/* Source Pills */}
        <div style={{ display: 'flex', gap: '4px', background: '#0D1117', padding: '2px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-color)' }}>
          <button
            style={{
              padding: '4px 10px',
              fontSize: '0.75rem',
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
              padding: '4px 10px',
              fontSize: '0.75rem',
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
              padding: '4px 10px',
              fontSize: '0.75rem',
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
      </div>
    </header>
  );
}
