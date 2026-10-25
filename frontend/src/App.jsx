import React, { useState, useEffect, useCallback, useRef } from 'react';
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

// Same idea as the backend title keys: accents, case, punctuation and VF/VOSTFR tags ignored
const normalizeTitle = (title) => (title || '')
  .normalize('NFD').replace(/[̀-ͯ]/g, '')
  .toLowerCase()
  .replace(/\((?:vf|vostfr)\)/g, ' ')
  .replace(/[^a-z0-9]+/g, ' ')
  .trim()
  .replace(/\s+(?:vf|vostfr)$/, '');

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
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
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

  // Same fallback id as the modals and the backend, so shelves read the bucket the player writes to
  const userId = currentUser?.id || 'default';

  // Save active user to localStorage when changed
  const handleSelectUser = (user) => {
    setCurrentUser(user);
    try {
      if (user) {
        localStorage.setItem('nami_active_user', JSON.stringify(user));
      } else {
        localStorage.removeItem('nami_active_user');
      }
    } catch {}
  };

  // Check if users exist on startup, force AuthModal if zero users or not logged in
  useEffect(() => {
    fetch('/api/users')
      .then((res) => res.json())
      .then((data) => {
        const uList = data || [];
        if (uList.length === 0) {
          setCurrentUser(null);
          try { localStorage.removeItem('nami_active_user'); } catch {}
          setIsAuthOpen(true);
        } else if (!currentUser || !uList.some((u) => u.id === currentUser.id)) {
          setCurrentUser(null);
          setIsAuthOpen(true);
        }
      })
      .catch(() => {});
  }, []);

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

  // History entries only store a title: find the matching catalogue entry (recents first, then search).
  // strict: only an exact (normalized) title match, never "the best search hit".
  const findAnimeByTitle = async (title, { strict = false } = {}) => {
    const wanted = normalizeTitle(title);
    const sameTitle = (a) => a.title && normalizeTitle(a.title) === wanted;
    const recentMatch = recentAnimes.find(sameTitle);
    if (recentMatch && recentMatch.url && recentMatch.source) return recentMatch;

    const searchRes = await fetch(`/api/search?q=${encodeURIComponent(title)}`);
    if (!searchRes.ok) return null;
    const searchData = await searchRes.json();
    const match = (searchData.results || []).find(sameTitle) || (strict ? null : searchData.results?.[0]);
    return match && match.url && match.source ? match : null;
  };

  // Ignores lookups that finish after the user already opened (or closed) another anime
  const selectRequestRef = useRef(0);

  const handleSelectAnime = async (anime) => {
    const request = ++selectRequestRef.current;
    if (anime?.url && anime?.source) {
      setSelectedAnime(anime);
      return;
    }
    try {
      const match = await findAnimeByTitle(anime?.title, { strict: true });
      if (request !== selectRequestRef.current) return;
      if (match) {
        setSelectedAnime({ ...match, cover: match.cover || anime.cover });
      } else if (anime?.title) {
        // No confident match: let the user pick the entry from a catalogue search
        setSearchQuery(anime.title);
        setActiveTab('catalog');
        loadCatalog(anime.title, activeSource);
      }
    } catch (e) {
      console.warn("Could not open anime details:", e);
    }
  };

  const handleCloseAnime = () => {
    selectRequestRef.current += 1;
    setSelectedAnime(null);
    loadUserShelves();
  };

  const handleApisReady = () => {
    loadCatalog(searchQuery, activeSource);
    loadRandomSuggestions();
    loadUserShelves();
  };

  const handleResumeFromShelf = async (item) => {
    const initialEp = {
      num: item.episode_num,
      title: `Épisode ${item.episode_num}`,
      embed_url: item.embed_url,
      file_path: item.file_path
    };

    setActivePlayer({
      animeTitle: item.anime_title,
      cover: item.cover,
      season: item.season,
      episode: initialEp,
      episodes: [initialEp],
      initialTime: item.position_sec,
      initialFilePath: item.file_path
    });

    // Background hydrate full season episodes so auto-advance and episode drawer work seamlessly
    try {
      let animeDetails = null;
      const match = await findAnimeByTitle(item.anime_title);
      if (match) {
        const res = await fetch(
          `/api/details?url=${encodeURIComponent(match.url)}&source=${encodeURIComponent(match.source)}`,
          { headers: { 'X-User-ID': userId } }
        );
        if (res.ok) animeDetails = await res.json();
      }

      if (animeDetails) {
        let fullEps = [];
        if (animeDetails.episodes && animeDetails.episodes.length > 0) {
          fullEps = animeDetails.episodes;
        } else if (animeDetails.seasons && animeDetails.seasons.length > 0) {
          const matchedSeason = animeDetails.seasons.find((s) => s.name === item.season) || animeDetails.seasons[0];
          const epsRes = await fetch(
            `/api/episodes?season_url=${encodeURIComponent(matchedSeason.url || matchedSeason.raw_link)}&anime_title=${encodeURIComponent(item.anime_title)}&season_name=${encodeURIComponent(matchedSeason.name)}`
          );
          if (epsRes.ok) {
            const epsData = await epsRes.json();
            fullEps = epsData.episodes || [];
          }
        }

        if (fullEps && fullEps.length > 0) {
          setActivePlayer((prev) => {
            if (!prev || prev.animeTitle !== item.anime_title) return prev;
            const matchedEp = fullEps.find((e) => String(e.num) === String(item.episode_num)) || prev.episode;
            return {
              ...prev,
              episode: { ...matchedEp, file_path: prev.episode?.file_path || matchedEp.file_path },
              episodes: fullEps
            };
          });
        }
      }
    } catch (e) {
      console.warn("Could not background hydrate episodes for resume:", e);
    }
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
        onApisReady={handleApisReady}
      />

      <main style={{ flex: 1, padding: '0 24px', maxWidth: '1440px', width: '100%', margin: '0 auto' }}>
        {activeTab === 'catalog' ? (
          <CatalogGrid
            results={results}
            isLoading={isLoading}
            searchQuery={searchQuery}
            activeSource={activeSource}
            continueWatching={continueWatching}
            recentAnimes={recentAnimes}
            randomSuggestions={randomSuggestions}
            onRollRandom={loadRandomSuggestions}
            onSelectAnime={handleSelectAnime}
            onResumeEpisode={handleResumeFromShelf}
          />
        ) : activeTab === 'history' ? (
          <HistoryView
            currentUser={currentUser}
            onSelectAnime={handleSelectAnime}
            onPlayEpisode={(title, season, ep, eps, cover, time, filePath) =>
              handlePlayEpisode(title, season, ep, eps, cover, time, filePath)
            }
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
          onClose={handleCloseAnime}
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
            setActivePlayer((prev) => ({ ...prev, episode: nextEp, initialTime: 0, initialFilePath: nextEp.file_path || null }));
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
