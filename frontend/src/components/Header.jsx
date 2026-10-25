import React, { useState, useEffect, useRef } from 'react';
import { Search, Download, Settings, RefreshCw, Home, History, BarChart3, HardDrive, Bookmark, X } from 'lucide-react';

const SOURCES = [
  { key: 'all', label: 'Toutes les sources' },
  { key: 'anime_sama', label: 'Anime-Sama' },
  { key: 'voiranime', label: 'VoirAnime' }
];

export default function Header({
  searchQuery,
  setSearchQuery,
  onSearch,
  activeSource,
  setActiveSource,
  activeTab,
  setActiveTab,
  activeDownloadsCount,
  watchlistCount,
  onOpenDownloads,
  onOpenSettings,
  onOpenStats,
  currentUser,
  onOpenAuth,
  onApisReady
}) {
  const [catalogStatus, setCatalogStatus] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const apisReadyRef = useRef(null);
  const onApisReadyRef = useRef(onApisReady);
  onApisReadyRef.current = onApisReady;

  useEffect(() => {
    let timer = null;
    let cancelled = false;
    const checkStatus = () => {
      fetch('/api/catalog/status')
        .then((res) => res.json())
        .then((data) => {
          setCatalogStatus(data);
          setIsRefreshing(Boolean(data.is_updating));
          // The server answers before the scraper APIs are up: reload once they are
          if (data.apis_ready === true && apisReadyRef.current === false) {
            onApisReadyRef.current?.();
          }
          if (typeof data.apis_ready === 'boolean') apisReadyRef.current = data.apis_ready;
        })
        .catch(() => {})
        .finally(() => {
          if (!cancelled) timer = setTimeout(checkStatus, apisReadyRef.current === false ? 3000 : 12000);
        });
    };

    checkStatus();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  const handleRefreshCatalog = () => {
    setIsRefreshing(true);
    fetch(`/api/catalog/update?source=${activeSource}`, { method: 'POST' })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => setCatalogStatus(data))
      .catch((err) => {
        console.error("Error launching refresh:", err);
        setIsRefreshing(false);
      });
  };

  const tabs = [
    { key: 'catalog', label: 'Accueil', icon: <Home size={15} /> },
    { key: 'history', label: 'Historique', icon: <History size={15} /> },
    { key: 'watchlist', label: 'À regarder plus tard', icon: <Bookmark size={15} />, count: watchlistCount },
    { key: 'offline', label: 'Hors-ligne', icon: <HardDrive size={15} /> }
  ];
  const refreshLabel = isRefreshing ? 'Mise à jour du catalogue...' : 'Mettre à jour le catalogue depuis les sources';

  return (
    <header className="app-header" style={{
      position: 'sticky',
      top: 0,
      zIndex: 40,
      display: 'flex',
      flexDirection: 'column',
      gap: '10px',
      background: 'rgba(15, 15, 15, 0.95)',
      backdropFilter: 'blur(12px)',
      borderBottom: '1px solid rgba(255, 255, 255, 0.06)'
    }}>
      <div className="app-header-row">
        {/* Logo */}
        <button
          type="button"
          aria-label="Accueil"
          style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}
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
          <span className="logo-badge" style={{
            fontSize: '0.68rem',
            background: 'rgba(255,255,255,0.08)',
            color: 'var(--text-muted)',
            padding: '2px 6px',
            borderRadius: '4px',
            fontWeight: 600
          }}>
            Self-Host
          </span>
        </button>

        {/* Search pill */}
        <form
          className="search-pill"
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            onSearch();
          }}
        >
          <div className="search-pill-field">
            <input
              type="text"
              enterKeyHint="search"
              aria-label="Rechercher un anime"
              placeholder="Rechercher un anime (Frieren, Solo Leveling...)"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button
                type="button"
                className="icon-btn"
                aria-label="Effacer la recherche"
                onClick={() => setSearchQuery('')}
                style={{ position: 'absolute', right: '2px', top: '2px', width: '36px', height: '36px' }}
              >
                <X size={16} />
              </button>
            )}
          </div>
          <button type="submit" className="search-pill-submit" aria-label="Rechercher" title="Rechercher">
            <Search size={18} />
          </button>
        </form>

        {/* Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <button
            type="button"
            className="icon-btn"
            onClick={handleRefreshCatalog}
            disabled={isRefreshing}
            aria-label={refreshLabel}
            title={refreshLabel}
          >
            <RefreshCw size={19} className={isRefreshing ? 'animate-spin' : ''} />
          </button>

          <button type="button" className="icon-btn" onClick={onOpenDownloads} aria-label="Téléchargements" title="Téléchargements">
            <Download size={19} />
            {activeDownloadsCount > 0 && <span className="icon-btn-badge">{activeDownloadsCount}</span>}
          </button>

          <button type="button" className="icon-btn" onClick={onOpenStats} aria-label="Mes statistiques de visionnage" title="Mes statistiques de visionnage">
            <BarChart3 size={19} />
          </button>

          <button type="button" className="icon-btn" onClick={onOpenSettings} aria-label="Paramètres" title="Paramètres">
            <Settings size={19} />
          </button>

          {/* Profile */}
          <button
            type="button"
            className="icon-btn"
            onClick={onOpenAuth}
            aria-label={currentUser?.username ? `Profil ${currentUser.username} : changer de profil` : 'Se connecter'}
            title={currentUser?.username ? `${currentUser.username} — changer de profil` : 'Se connecter'}
            style={{ marginLeft: '4px' }}
          >
            {currentUser?.avatar && currentUser.avatar.startsWith('data:') ? (
              <img
                src={currentUser.avatar}
                alt=""
                style={{ width: '32px', height: '32px', borderRadius: '50%', objectFit: 'cover' }}
              />
            ) : (
              <span style={{
                width: '32px',
                height: '32px',
                borderRadius: '50%',
                background: 'rgba(255,255,255,0.1)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.05rem'
              }}>
                {currentUser?.avatar || '👤'}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Chips: the sections, then the catalogue's source filter */}
      <nav className="chip-row" aria-label="Navigation">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={`chip${activeTab === tab.key ? ' active' : ''}`}
            aria-current={activeTab === tab.key ? 'page' : undefined}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.icon} {tab.label}
            {tab.count > 0 && <span className="chip-count">{tab.count}</span>}
          </button>
        ))}
        {activeTab === 'catalog' && (
          <>
            <span className="chip-divider" aria-hidden="true" />
            {SOURCES.map((src) => (
              <button
                key={src.key}
                type="button"
                className={`chip${activeSource === src.key ? ' active' : ''}`}
                aria-pressed={activeSource === src.key}
                onClick={() => setActiveSource(src.key)}
              >
                {src.label}
              </button>
            ))}
          </>
        )}
      </nav>
    </header>
  );
}
