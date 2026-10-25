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
import { normalizeTitle, titleKey } from './utils/titles';

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
    // Entities carry every known name of the anime (other sources, alternative titles)
    const sameTitle = (a) => [a.title, ...(a.alt_titles || [])].some((t) => t && normalizeTitle(t) === wanted);
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

    // Background hydrate the season's episodes so auto-advance and the episode drawer work.
    // The playing episode is never replaced: that would restart its playback.
    try {
      const match = await findAnimeByTitle(item.anime_title);
      if (!match?.id) return;
      const res = await fetch(`/api/anime/${encodeURIComponent(match.id)}`, { headers: { 'X-User-ID': userId } });
      if (!res.ok) return;
      const details = await res.json();

      // The season variant this record was saved under (its history keys), from the record's source
      const wanted = titleKey(item.anime_title);
      const fromVoirAnime = (item.embed_url || '').includes('voir-anime');
      let found = null;
      (details.seasons || []).forEach((season) => {
        (season.variants || []).forEach((variant) => {
          if (variant.version === 'scans') return;
          const savedHere = (variant.history_keys || []).some((k) => titleKey(k.title) === wanted && k.season === item.season);
          if (savedHere && (!found || (variant.source === 'voiranime') === fromVoirAnime)) found = { season, variant };
        });
      });
      if (!found) return;

      const params = new URLSearchParams({ season: found.season.key, source: found.variant.source, version: found.variant.version });
      const epsRes = await fetch(`/api/anime/${encodeURIComponent(details.id)}/episodes?${params}`);
      if (!epsRes.ok) return;
      const fullEps = (await epsRes.json()).episodes || [];
      if (fullEps.length > 0) {
        setActivePlayer((prev) => (
          prev && prev.animeTitle === item.anime_title && prev.season === item.season ? { ...prev, episodes: fullEps } : prev
        ));
      }
    } catch (e) {
      console.warn("Could not background hydrate episodes for resume:", e);
    }
  };

  // Other players of an episode, tried by the download when the first one has no direct stream
  const fallbackUrls = (episode, primary) =>
    (episode.players || []).map((p) => p.embed_url).filter((url) => url && url !== primary);

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
            stream_type: streamType,
            fallback_urls: data.stream_url ? [] : fallbackUrls(episode, embedUrl)
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
      stream_type: 'm3u8',
      fallback_urls: fallbackUrls(ep, ep.embed_url || ep.url)
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
