import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import CatalogGrid from './components/CatalogGrid';
import AnimeDetailModal from './components/AnimeDetailModal';
import VideoPlayerModal from './components/VideoPlayerModal';
import DownloadManagerDrawer from './components/DownloadManagerDrawer';
import SettingsModal from './components/SettingsModal';

export default function App() {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeSource, setActiveSource] = useState('all');
  const [results, setResults] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  // Modals & Drawers state
  const [selectedAnime, setSelectedAnime] = useState(null);
  const [activePlayer, setActivePlayer] = useState(null); // { anime, season, episode, episodes }
  const [isDownloadsOpen, setIsDownloadsOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // Downloads state
  const [downloads, setDownloads] = useState([]);

  // Fetch initial popular/recent items or run search
  const handleSearch = () => {
    if (!searchQuery.trim()) return;
    setIsLoading(true);

    fetch(`/api/search?q=${encodeURIComponent(searchQuery.trim())}&source=${activeSource}`)
      .then((res) => res.json())
      .then((data) => {
        setResults(data.results || []);
      })
      .catch((err) => console.error("Search error:", err))
      .finally(() => setIsLoading(false));
  };

  // Run search when source tab changes or initial query provided
  useEffect(() => {
    if (searchQuery.trim()) {
      handleSearch();
    } else {
      // Default search for popular anime on home load
      setIsLoading(true);
      fetch(`/api/search?q=Frieren&source=${activeSource}`)
        .then((res) => res.json())
        .then((data) => {
          setResults(data.results || []);
        })
        .catch((err) => console.error("Error fetching default anime:", err))
        .finally(() => setIsLoading(false));
    }
  }, [activeSource]);

  // Poll downloads status every 2 seconds
  useEffect(() => {
    const fetchDownloads = () => {
      fetch('/api/downloads')
        .then((res) => res.json())
        .then((data) => setDownloads(data || []))
        .catch((err) => console.error("Error fetching downloads:", err));
    };

    fetchDownloads();
    const interval = setInterval(fetchDownloads, 2000);
    return () => clearInterval(interval);
  }, []);

  const activeDownloadsCount = downloads.filter((d) => d.status === 'downloading' || d.status === 'queued').length;

  // Single episode play handler
  const handlePlayEpisode = (anime, season, episode, episodesList) => {
    setActivePlayer({
      anime,
      season,
      episode,
      episodes: episodesList
    });
  };

  // Single episode download handler
  const handleDownloadEpisode = (animeTitle, season, episode) => {
    const embedUrl = episode.embed_url || episode.url;

    fetch(`/api/resolve?embed_url=${encodeURIComponent(embedUrl)}&source=anime_sama`)
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
            episode_num: episode.num || episode.title || '1',
            stream_url: streamUrl,
            stream_type: streamType
          })
        });
      })
      .then(() => {
        setIsDownloadsOpen(true);
      })
      .catch((err) => console.error("Error launching download:", err));
  };

  // Bulk season download handler
  const handleDownloadBulk = (animeTitle, season, episodesList) => {
    const payloadEpisodes = episodesList.map((ep) => ({
      episode_num: ep.num || ep.title || '1',
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

  const handleCancelDownload = (taskId) => {
    fetch(`/api/downloads/cancel/${taskId}`, { method: 'POST' });
  };

  const handleClearCompleted = () => {
    fetch('/api/downloads/clear', { method: 'POST' });
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        onSearch={handleSearch}
        activeSource={activeSource}
        setActiveSource={setActiveSource}
        activeDownloadsCount={activeDownloadsCount}
        onOpenDownloads={() => setIsDownloadsOpen(true)}
        onOpenSettings={() => setIsSettingsOpen(true)}
      />

      <main style={{ flex: 1, padding: '0 28px', maxWidth: '1440px', width: '100%', margin: '0 auto' }}>
        <CatalogGrid
          results={results}
          isLoading={isLoading}
          onSelectAnime={(anime) => setSelectedAnime(anime)}
        />
      </main>

      {/* Anime Detail Modal */}
      {selectedAnime && (
        <AnimeDetailModal
          anime={selectedAnime}
          onClose={() => setSelectedAnime(null)}
          onPlayEpisode={handlePlayEpisode}
          onDownloadEpisode={handleDownloadEpisode}
          onDownloadBulk={handleDownloadBulk}
        />
      )}

      {/* Video Player Modal */}
      {activePlayer && (
        <VideoPlayerModal
          anime={activePlayer.anime}
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

      {/* Download Manager Drawer */}
      <DownloadManagerDrawer
        isOpen={isDownloadsOpen}
        onClose={() => setIsDownloadsOpen(false)}
        downloads={downloads}
        onCancelTask={handleCancelDownload}
        onClearCompleted={handleClearCompleted}
      />

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  );
}
