import React, { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import CatalogGrid from './components/CatalogGrid';
import HistoryView from './components/HistoryView';
import AnimeDetailModal from './components/AnimeDetailModal';
import VideoPlayerModal from './components/VideoPlayerModal';
import DownloadManagerDrawer from './components/DownloadManagerDrawer';
import SettingsModal from './components/SettingsModal';

export default function App() {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeSource, setActiveSource] = useState('all');
  const [activeTab, setActiveTab] = useState('catalog');
  const [results, setResults] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  // Modals & Drawers
  const [selectedAnime, setSelectedAnime] = useState(null);
  const [activePlayer, setActivePlayer] = useState(null);
  const [isDownloadsOpen, setIsDownloadsOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // Downloads state
  const [downloads, setDownloads] = useState([]);

  // Load full catalog or search results
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

  // Reload catalog when source filter changes
  useEffect(() => {
    loadCatalog(searchQuery, activeSource);
  }, [activeSource]);

  // Poll downloads every 10s (not 2s)
  useEffect(() => {
    const fetchDownloads = () => {
      fetch('/api/downloads')
        .then((res) => res.json())
        .then((data) => setDownloads(data || []))
        .catch(() => {});
    };

    fetchDownloads();
    const interval = setInterval(fetchDownloads, 10000);
    return () => clearInterval(interval);
  }, []);

  const activeDownloadsCount = downloads.filter((d) => d.status === 'downloading' || d.status === 'queued').length;

  const handlePlayEpisode = (animeTitle, season, episode, episodesList) => {
    setActivePlayer({
      animeTitle,
      season,
      episode,
      episodes: episodesList
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
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
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
      />

      <main style={{ flex: 1, padding: '0 24px', maxWidth: '1400px', width: '100%', margin: '0 auto' }}>
        {activeTab === 'catalog' ? (
          <CatalogGrid
            results={results}
            isLoading={isLoading}
            onSelectAnime={(anime) => setSelectedAnime(anime)}
          />
        ) : (
          <HistoryView
            onSelectAnime={(anime) => setSelectedAnime(anime)}
            onPlayEpisode={(anime, season, ep, eps) => handlePlayEpisode(anime.title, season, ep, eps)}
          />
        )}
      </main>

      {selectedAnime && (
        <AnimeDetailModal
          anime={selectedAnime}
          onClose={() => setSelectedAnime(null)}
          onPlayEpisode={(animeTitle, season, ep, eps) => handlePlayEpisode(animeTitle, season, ep, eps)}
          onDownloadEpisode={handleDownloadEpisode}
          onDownloadBulk={handleDownloadBulk}
        />
      )}

      {activePlayer && (
        <VideoPlayerModal
          animeTitle={activePlayer.animeTitle}
          season={activePlayer.season}
          episode={activePlayer.episode}
          episodes={activePlayer.episodes}
          onClose={() => setActivePlayer(null)}
          onDownloadEpisode={handleDownloadEpisode}
          onSelectNextEpisode={(nextEp) => {
            setActivePlayer((prev) => ({ ...prev, episode: nextEp }));
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
    </div>
  );
}
