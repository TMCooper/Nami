import React, { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import CatalogGrid from './components/CatalogGrid';
import HistoryView from './components/HistoryView';
import OfflineLibraryView from './components/OfflineLibraryView';
import AnimeDetailModal from './components/AnimeDetailModal';
import VideoPlayerModal from './components/VideoPlayerModal';
import DownloadManagerDrawer from './components/DownloadManagerDrawer';
import SettingsModal from './components/SettingsModal';
import StatsModal from './components/StatsModal';
import AuthModal from './components/AuthModal';

export default function App() {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeSource, setActiveSource] = useState('all');
  const [activeTab, setActiveTab] = useState('catalog'); // 'catalog' | 'history' | 'offline'
  const [results, setResults] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  // Home Shelves State
  const [continueWatching, setContinueWatching] = useState([]);
  const [recentAnimes, setRecentAnimes] = useState([]);
  const [randomSuggestions, setRandomSuggestions] = useState([]);

  // User Authentication State
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const saved = localStorage.getItem('nami_active_user');
      return saved ? JSON.parse(saved) : { id: 'default', username: 'Utilisateur', avatar: '👤' };
    } catch {
      return { id: 'default', username: 'Utilisateur', avatar: '👤' };
    }
  });
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  // Modals & Drawers
  const [selectedAnime, setSelectedAnime] = useState(null);
  const [activePlayer, setActivePlayer] = useState(null);
  const [isDownloadsOpen, setIsDownloadsOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isStatsOpen, setIsStatsOpen] = useState(false);

  // Downloads state
  const [downloads, setDownloads] = useState([]);

  const userId = currentUser?.id || 'default';

  // Save active user to localStorage when changed
  const handleSelectUser = (user) => {
    setCurrentUser(user);
    try {
      localStorage.setItem('nami_active_user', JSON.stringify(user));
    } catch {}
  };

  // Fetch continue watching & recent items for current user
  const loadUserShelves = useCallback(() => {
    fetch('/api/history/continue', {
      headers: { 'X-User-ID': userId }
    })
      .then((res) => res.json())
      .then((data) => setContinueWatching(data.results || []))
      .catch(() => {});

    fetch('/api/catalog/recent', {
      headers: { 'X-User-ID': userId }
    })
      .then((res) => res.json())
      .then((data) => setRecentAnimes(data.results || []))
      .catch(() => {});
  }, [userId]);

  // Fetch random discovery suggestions
  const loadRandomSuggestions = useCallback(() => {
    fetch('/api/catalog/random?count=12')
      .then((res) => res.json())
      .then((data) => setRandomSuggestions(data.results || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadUserShelves();
    loadRandomSuggestions();
  }, [loadUserShelves, loadRandomSuggestions]);

  // Load catalog or search results
  const loadCatalog = useCallback((query = '', source = 'all') => {
    setIsLoading(true);
    const q = query.trim();
    const url = q
      ? `/api/search?q=${encodeURIComponent(q)}&source=${source}`
      : `/api/search?q=&source=${source}`;

    fetch(url)
      .then((res) => res.json())
      .then((data) => setResults(data.results || []))
      .catch((err) => console.error("Catalog load error:", err))
      .finally(() => setIsLoading(false));
  }, []);

  const handleSearch = () => {
    setActiveTab('catalog');
    loadCatalog(searchQuery, activeSource);
  };

  useEffect(() => {
    loadCatalog(searchQuery, activeSource);
  }, [activeSource]);

  // Poll downloads
  useEffect(() => {
    const fetchDownloads = () => {
      fetch('/api/downloads')
        .then((res) => res.json())
        .then((data) => setDownloads(data || []))
        .catch(() => {});
    };

    fetchDownloads();
    const interval = setInterval(fetchDownloads, 8000);
    return () => clearInterval(interval);
  }, []);

  const activeDownloadsCount = downloads.filter((d) => d.status === 'downloading' || d.status === 'queued').length;

  const handlePlayEpisode = (animeTitle, season, episode, episodesList, cover = '', initialTime = 0, initialFilePath = null) => {
    setActivePlayer({
      animeTitle,
      cover,
      season,
      episode,
      episodes: episodesList,
      initialTime,
      initialFilePath
    });
  };

  const handleResumeFromShelf = (item) => {
    setActivePlayer({
      animeTitle: item.anime_title,
      cover: item.cover,
      season: item.season,
      episode: {
        num: item.episode_num,
        title: `Épisode ${item.episode_num}`,
        embed_url: item.embed_url
      },
      episodes: [{ num: item.episode_num, title: `Épisode ${item.episode_num}`, embed_url: item.embed_url }],
      initialTime: item.position_sec,
      initialFilePath: item.file_path
    });
  };

  const handleDownloadEpisode = (animeTitle, season, episode) => {
    const embedUrl = episode.embed_url || episode.url;

    fetch(`/api/resolve?embed_url=${encodeURIComponent(embedUrl)}`)
      .then((res) => res.json())
      .then((data) => {
        const streamUrl = data.stream_url || embedUrl;
        const streamType = data.stream_type || 'm3u8';

        return fetch('/api/downloads', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            anime_title: animeTitle,
            season: season,
            episode_num: String(episode.num || episode.title || '1'),
            stream_url: streamUrl,
            stream_type: streamType
          })
        });
      })
      .then(() => setIsDownloadsOpen(true))
      .catch((err) => console.error("Error launching download:", err));
  };

  const handleDownloadBulk = (animeTitle, season, episodesList) => {
    const payloadEpisodes = episodesList.map((ep) => ({
      episode_num: String(ep.num || ep.title || '1'),
      stream_url: ep.embed_url || ep.url,
      stream_type: 'm3u8'
    }));

    fetch('/api/downloads/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        anime_title: animeTitle,
        season: season,
        episodes: payloadEpisodes
      })
    })
      .then(() => setIsDownloadsOpen(true))
      .catch((err) => console.error("Error bulk downloading:", err));
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-main)' }}>
      <Header
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        onSearch={handleSearch}
        activeSource={activeSource}
        setActiveSource={setActiveSource}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        activeDownloadsCount={activeDownloadsCount}
        onOpenDownloads={() => setIsDownloadsOpen(true)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenStats={() => setIsStatsOpen(true)}
        currentUser={currentUser}
        onOpenAuth={() => setIsAuthOpen(true)}
      />

      <main style={{ flex: 1, padding: '0 24px', maxWidth: '1440px', width: '100%', margin: '0 auto' }}>
        {activeTab === 'catalog' ? (
          <CatalogGrid
            results={results}
            isLoading={isLoading}
            searchQuery={searchQuery}
            continueWatching={continueWatching}
            recentAnimes={recentAnimes}
            randomSuggestions={randomSuggestions}
            onRollRandom={loadRandomSuggestions}
            onSelectAnime={(anime) => setSelectedAnime(anime)}
            onResumeEpisode={handleResumeFromShelf}
          />
        ) : activeTab === 'history' ? (
          <HistoryView
            currentUser={currentUser}
            onSelectAnime={(anime) => setSelectedAnime(anime)}
            onPlayEpisode={(anime, season, ep, eps) => handlePlayEpisode(anime.title, season, ep, eps, anime.cover, 0)}
          />
        ) : (
          <OfflineLibraryView
            onPlayEpisode={(title, season, ep, eps, cover, time, filePath) =>
              handlePlayEpisode(title, season, ep, eps, cover, time, filePath)
            }
          />
        )}
      </main>

      {selectedAnime && (
        <AnimeDetailModal
          currentUser={currentUser}
          anime={selectedAnime}
          onClose={() => {
            setSelectedAnime(null);
            loadUserShelves();
          }}
          onPlayEpisode={(animeTitle, season, ep, eps, cover, time, filePath) => {
            handlePlayEpisode(animeTitle, season, ep, eps, cover, time, filePath);
            loadUserShelves();
          }}
          onDownloadEpisode={handleDownloadEpisode}
          onDownloadBulk={handleDownloadBulk}
        />
      )}

      {activePlayer && (
        <VideoPlayerModal
          currentUser={currentUser}
          animeTitle={activePlayer.animeTitle}
          cover={activePlayer.cover}
          season={activePlayer.season}
          episode={activePlayer.episode}
          episodes={activePlayer.episodes}
          initialTime={activePlayer.initialTime}
          initialFilePath={activePlayer.initialFilePath}
          onClose={() => {
            setActivePlayer(null);
            loadUserShelves();
          }}
          onDownloadEpisode={handleDownloadEpisode}
          onSelectNextEpisode={(nextEp) => {
            setActivePlayer((prev) => ({ ...prev, episode: nextEp, initialTime: 0, initialFilePath: null }));
          }}
        />
      )}

      <DownloadManagerDrawer
        isOpen={isDownloadsOpen}
        onClose={() => setIsDownloadsOpen(false)}
        downloads={downloads}
        onCancelTask={(id) => fetch(`/api/downloads/cancel/${id}`, { method: 'POST' })}
        onClearCompleted={() => fetch('/api/downloads/clear', { method: 'POST' })}
      />

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />

      <StatsModal
        isOpen={isStatsOpen}
        onClose={() => setIsStatsOpen(false)}
        currentUser={currentUser}
      />

      <AuthModal
        isOpen={isAuthOpen}
        onClose={() => setIsAuthOpen(false)}
        currentUser={currentUser}
        onSelectUser={handleSelectUser}
      />
    </div>
  );
}
