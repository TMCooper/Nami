import React, { useState, useEffect } from 'react';
import { Search, Download, Settings, RefreshCw, Layers, History } from 'lucide-react';

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
        {/* Sober Minimalist Logo */}
        <div 
          style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}
          onClick={() => {
            setSearchQuery('');
            setActiveTab('catalog');
          }}
        >
          <span style={{
            fontSize: '1.25rem',
            fontWeight: 800,
            letterSpacing: '1px',
            color: '#F0F6FC'
          }}>
            NAMI
          </span>
        </div>

        {/* Search Bar */}
        <div style={{ position: 'relative', flex: 1, maxWidth: '480px' }}>
          <Search size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="Rechercher un anime (ex: Frieren, Solo Leveling)..."
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
              outline: 'none'
            }}
          />
        </div>

        {/* Top Right Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Refresh Catalog Button */}
          <button
            className="btn btn-secondary"
            onClick={handleRefreshCatalog}
            disabled={isRefreshing}
            style={{ fontSize: '0.78rem', padding: '6px 12px' }}
            title="Actualiser la base de données d'animes"
          >
            <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />
            <span>{isRefreshing ? 'Actualisation...' : 'Actualiser DB'}</span>
          </button>

          {/* Downloads Drawer Button */}
          <button
            className="btn btn-secondary"
            onClick={onOpenDownloads}
            style={{ position: 'relative', fontSize: '0.78rem', padding: '6px 12px' }}
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
          <button className="btn btn-icon btn-secondary" onClick={onOpenSettings} title="Paramètres" style={{ width: '32px', height: '32px' }}>
            <Settings size={14} />
          </button>
        </div>
      </div>

      {/* Bottom Row: Navigation Tabs & Source Selector */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '4px', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
        {/* Nav Tabs */}
        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            className={`btn ${activeTab === 'catalog' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '5px 12px', fontSize: '0.8rem' }}
            onClick={() => setActiveTab('catalog')}
          >
            <Layers size={13} /> Catalogue
          </button>

          <button
            className={`btn ${activeTab === 'history' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '5px 12px', fontSize: '0.8rem' }}
            onClick={() => setActiveTab('history')}
          >
            <History size={13} /> Historique & Reprise
          </button>
        </div>

        {/* Source Pills */}
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
      </div>
    </header>
  );
}
