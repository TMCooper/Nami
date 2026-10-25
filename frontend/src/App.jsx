import React, { useState, useEffect, useCallback, useRef, useMemo, lazy, Suspense } from 'react';
import { Loader2 } from 'lucide-react';
import Header from './components/Header';
import CatalogGrid from './components/CatalogGrid';
import DownloadManagerDrawer from './components/DownloadManagerDrawer';
import SettingsModal from './components/SettingsModal';
import StatsModal from './components/StatsModal';
import AuthModal from './components/AuthModal';
import { normalizeTitle } from './utils/titles';
import { animeKeys, sameAnime, watchlistPayload } from './utils/animes';

// Loaded on demand: the player alone carries hls.js (about two thirds of the app's code)
const loadDetail = () => import('./components/AnimeDetailModal');
const loadPlayer = () => import('./components/VideoPlayerModal');
const AnimeDetailModal = lazy(loadDetail);
const VideoPlayerModal = lazy(loadPlayer);
const HistoryView = lazy(() => import('./components/HistoryView'));
const WatchlistView = lazy(() => import('./components/WatchlistView'));
const OfflineLibraryView = lazy(() => import('./components/OfflineLibraryView'));

const TabFallback = () => (
  <div style={{ padding: '80px 0', display: 'flex', justifyContent: 'center' }}>
    <Loader2 className="animate-spin" size={26} color="var(--text-muted)" />
  </div>
);

const RESTORE_WINDOW_MS = 60000; // a re-add this soon after a removal is an undo: the anime keeps its place

export default function App() {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeSource, setActiveSource] = useState('all');
  const [activeTab, setActiveTab] = useState('catalog'); // 'catalog' | 'history' | 'watchlist' | 'offline'
  const [results, setResults] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  // Home Shelves State
  const [continueWatching, setContinueWatching] = useState([]);
  const [recentAnimes, setRecentAnimes] = useState([]);
  const [randomSuggestions, setRandomSuggestions] = useState([]);
  const [watchlist, setWatchlist] = useState([]);
  const [resumingKey, setResumingKey] = useState(null); // continue card waiting for its season list
  const [notice, setNotice] = useState('');

  const watchlistRef = useRef([]);
  watchlistRef.current = watchlist;
  // Only the latest request of a kind may set its state (profile switches, fast taps)
  const shelvesRequestRef = useRef(0);
  const watchlistRequestRef = useRef(0);
  const removedRef = useRef(new Map()); // identity key -> { addedAt, removedAt }: an undone removal keeps its place
  const confirmedRef = useRef([]); // last list the server returned: what a failed toggle reverts to
  const resumeTokenRef = useRef(0); // bumped by every newer action: a slow resume then gives up
  const noticeTimerRef = useRef(null);

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
  const userIdRef = useRef(userId);
  userIdRef.current = userId;

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

  // The anime page and the player are fetched once the home screen is idle: the first tap opens them at once
  useEffect(() => {
    const prefetch = () => { loadDetail(); loadPlayer(); };
    if ('requestIdleCallback' in window) {
      const id = window.requestIdleCallback(prefetch, { timeout: 5000 });
      return () => window.cancelIdleCallback(id);
    }
    const timer = setTimeout(prefetch, 3000);
    return () => clearTimeout(timer);
  }, []);

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

  const showNotice = (text) => {
    setNotice(text);
    clearTimeout(noticeTimerRef.current);
    noticeTimerRef.current = setTimeout(() => setNotice(''), 4000);
  };

  // Any successful response is a server state of that profile, even when a newer request supersedes it
  const confirmWatchlist = (profile, list) => {
    if (profile === userIdRef.current) confirmedRef.current = list;
  };

  const loadWatchlist = useCallback(() => {
    const request = ++watchlistRequestRef.current;
    const profile = userId;
    fetch('/api/watchlist', {
      headers: { 'X-User-ID': profile }
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        confirmWatchlist(profile, data.results || []);
        if (request === watchlistRequestRef.current) setWatchlist(data.results || []);
      })
      .catch(() => {});
  }, [userId]);

  // Fetch continue watching, recent items & watchlist for current user
  const loadUserShelves = useCallback(() => {
    const request = ++shelvesRequestRef.current;
    // Not only the home shelf (8 cards): the watchlist tab finds each item's resume card in this list
    fetch('/api/history/continue?limit=100', {
      headers: { 'X-User-ID': userId }
    })
      .then((res) => res.json())
      .then((data) => {
        if (request === shelvesRequestRef.current) setContinueWatching(data.results || []);
      })
      .catch(() => {});

    fetch('/api/catalog/recent', {
      headers: { 'X-User-ID': userId }
    })
      .then((res) => res.json())
      .then((data) => {
        if (request === shelvesRequestRef.current) setRecentAnimes(data.results || []);
      })
      .catch(() => {});

    loadWatchlist();
  }, [userId, loadWatchlist]);

  // Fetch random discovery suggestions
  const loadRandomSuggestions = useCallback(() => {
    fetch('/api/catalog/random?count=12')
      .then((res) => res.json())
      .then((data) => setRandomSuggestions(data.results || []))
      .catch(() => {});
  }, []);

  // The previous profile's shelves disappear at once, not when the new responses arrive
  useEffect(() => {
    setContinueWatching([]);
    setRecentAnimes([]);
    setWatchlist([]);
    confirmedRef.current = [];
    removedRef.current.clear();
    resumeTokenRef.current += 1; // a pending resume belongs to the previous profile
    setResumingKey(null);
  }, [userId]);

  useEffect(() => {
    loadUserShelves();
    loadRandomSuggestions();
  }, [loadUserShelves, loadRandomSuggestions]);

  // O(1) per card: one URL parse per card per render
  const watchlistKeys = useMemo(() => new Set(watchlist.flatMap(animeKeys)), [watchlist]);
  const isInWatchlist = useCallback((anime) => animeKeys(anime).some((k) => watchlistKeys.has(k)), [watchlistKeys]);

  // Optimistic: the latest request wins; a failure reverts to the server's last list, then resyncs.
  // restore: the re-add of a ghost in the watchlist tab (an undone removal).
  const handleToggleWatchlist = (anime, { restore = false } = {}) => {
    const previous = watchlistRef.current;
    const saved = previous.find((w) => sameAnime(w, anime));
    const request = ++watchlistRequestRef.current;
    const profile = userId;
    let call;
    if (saved) {
      const removed = { addedAt: saved.added_at, removedAt: Date.now() };
      animeKeys(saved).forEach((k) => removedRef.current.set(k, removed));
      setWatchlist(previous.filter((w) => !sameAnime(w, anime)));
      const params = new URLSearchParams({ id: saved.id || '', source: saved.source || '', url: saved.url || '' });
      call = fetch(`/api/watchlist?${params}`, { method: 'DELETE', headers: { 'X-User-ID': userId } });
    } else {
      // An undo (ghost tap, or a re-add within a minute) keeps the old place; a later re-add is a new add
      const removed = animeKeys(anime).map((k) => removedRef.current.get(k)).find(Boolean);
      const undo = removed && (restore || Date.now() - removed.removedAt < RESTORE_WINDOW_MS);
      const addedAt = (undo && removed.addedAt) || null;
      const optimistic = [{ ...anime, added_at: addedAt || Date.now() / 1000 }, ...previous].sort((a, b) => b.added_at - a.added_at);
      setWatchlist(optimistic);
      call = fetch('/api/watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-ID': userId },
        body: JSON.stringify({ user_id: userId, anime: watchlistPayload(anime), added_at: addedAt })
      });
    }
    call
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        confirmWatchlist(profile, data.results || []);
        if (request === watchlistRequestRef.current) setWatchlist(data.results || []);
      })
      .catch(() => {
        // Not the previous optimistic list: an earlier toggle in it may have failed too
        if (request === watchlistRequestRef.current) {
          setWatchlist(confirmedRef.current);
          loadWatchlist();
        }
        showNotice('Impossible de mettre à jour la liste.');
      });
  };

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

  // context: the play context (entity, season variant, history keys) when the caller knows it
  const handlePlayEpisode = (animeTitle, season, episode, episodesList, cover = '', initialTime = 0, initialFilePath = null, context = null) => {
    resumeTokenRef.current += 1; // a pending shelf resume must not replace this player
    setActivePlayer({
      animeTitle,
      cover,
      season,
      episode,
      episodes: episodesList,
      initialTime,
      initialFilePath,
      autoResume: false,
      context,
      fallbackPlayers: null
    });
  };

  // History entries only store a title: find the matching catalogue entry (recents first, then search).
  // Only an exact (normalized) title match, never "the best search hit".
  const findAnimeByTitle = async (title) => {
    const wanted = normalizeTitle(title);
    // Entities carry every known name of the anime (other sources, alternative titles)
    const sameTitle = (a) => [a.title, ...(a.alt_titles || [])].some((t) => t && normalizeTitle(t) === wanted);
    const recentMatch = recentAnimes.find(sameTitle);
    if (recentMatch && recentMatch.url && recentMatch.source) return recentMatch;

    const searchRes = await fetch(`/api/search?q=${encodeURIComponent(title)}`);
    if (!searchRes.ok) return null;
    const searchData = await searchRes.json();
    const match = (searchData.results || []).find(sameTitle);
    return match && match.url && match.source ? match : null;
  };

  // Ignores lookups that finish after the user already opened (or closed) another anime
  const selectRequestRef = useRef(0);

  const handleSelectAnime = async (anime) => {
    const request = ++selectRequestRef.current;
    resumeTokenRef.current += 1; // a pending shelf resume must not open over this page
    if (anime?.url && anime?.source) {
      setSelectedAnime(anime);
      return;
    }
    try {
      const match = await findAnimeByTitle(anime?.title);
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

  // The season list of a continue item, resolved by the server from the stored link (strict, no recents)
  const fetchResume = async (item, timeoutMs) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const params = new URLSearchParams({ anime_title: item.anime_title, season: item.season });
      const res = await fetch(`/api/history/resume?${params}`, { headers: { 'X-User-ID': userId }, signal: controller.signal });
      if (!res.ok) return null;
      const data = await res.json();
      return data.exact ? data : null; // never attach a list from another source or version
    } catch {
      return null;
    } finally {
      clearTimeout(timer);
    }
  };

  const contextFromResume = (data) => ({
    anime: data.anime,
    seasonKey: data.season.key,
    source: data.variant.source,
    version: data.variant.version,
    historyKeys: data.variant.history_keys || [],
    via: 'resume',
    fullSeason: true
  });
  const sameEpisode = (ep, num) => String(ep.num || ep.title || '1') === String(num);
  const openAnimeOf = (item) => handleSelectAnime(
    item.anime ? { ...item.anime, cover: item.cover } : { title: item.display_title || item.anime_title, cover: item.cover }
  );

  // Continue cards, watchlist and history rows: play at once and seek, like YouTube
  const handleResumeEpisode = async (item) => {
    const epNum = String(item.episode_num ?? '');
    // A non-numeric id is a raw source title (episode 0, specials): same rule as the backend's episode titles
    const rawNum = epNum.match(/-\s*(\d+)\s*(?:vostfr|vf)\b/i);
    const playing = {
      num: item.episode_num,
      title: item.episode_title
        || (/^\d+$/.test(epNum) ? `Épisode ${epNum}` : rawNum ? `Épisode ${parseInt(rawNum[1], 10)}` : 'Épisode spécial'),
      synthetic_title: !item.episode_title, // display only: never saved as the episode's own title
      embed_url: item.embed_url,
      file_path: item.file_path
    };
    if (!item.is_next && (item.embed_url || item.file_path)) {
      resumeTokenRef.current += 1; // this player supersedes a pending resume
      const linked = Boolean(item.anime?.id);
      // Opens at once and seeks to the stored position; the season list and host fallbacks arrive later
      setActivePlayer({
        animeTitle: item.anime_title,
        cover: item.cover,
        season: item.season,
        episode: playing,
        episodes: [playing],
        initialTime: item.position_sec || 0,
        initialFilePath: item.file_path || null,
        autoResume: true,
        context: null,
        fallbackPlayers: linked ? null : [] // []: no other host will come, the player need not wait for them
      });
      if (!linked) return; // unlinked record: the stored episode only, never a guess
      const data = await fetchResume(item, 15000);
      const full = data?.episodes.find((ep) => sameEpisode(ep, item.episode_num));
      // The playing episode is never replaced: that would restart its playback
      setActivePlayer((prev) => (
        prev && prev.animeTitle === item.anime_title && prev.season === item.season && sameEpisode(prev.episode, item.episode_num)
          ? data
            ? { ...prev, episodes: data.episodes, context: contextFromResume(data), fallbackPlayers: full?.players || [] }
            : { ...prev, fallbackPlayers: [] }
          : prev
      ));
      return;
    }
    if (resumingKey) return; // taps during a pending resume are ignored
    const token = ++resumeTokenRef.current;
    setResumingKey(item.key);
    try {
      const data = item.anime?.id ? await fetchResume(item, 8000) : null;
      if (token !== resumeTokenRef.current) return; // the user played, opened or closed something meanwhile
      const ep = data?.episodes.find((e) => sameEpisode(e, item.episode_num));
      if (ep) {
        setActivePlayer({
          animeTitle: item.anime_title,
          cover: item.cover,
          season: item.season,
          episode: ep,
          episodes: data.episodes,
          initialTime: item.is_next ? 0 : (item.position_sec || 0),
          initialFilePath: null,
          autoResume: !item.is_next,
          context: contextFromResume(data),
          fallbackPlayers: null
        });
      } else {
        openAnimeOf(item); // timeout, 404 or variant no longer served
      }
    } finally {
      setResumingKey((key) => (key === item.key ? null : key));
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
        watchlistCount={watchlist.length}
        onOpenDownloads={() => setIsDownloadsOpen(true)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenStats={() => setIsStatsOpen(true)}
        currentUser={currentUser}
        onOpenAuth={() => setIsAuthOpen(true)}
        onApisReady={handleApisReady}
      />

      <main style={{ flex: 1, padding: '0 24px', maxWidth: '1440px', width: '100%', margin: '0 auto' }}>
        <Suspense fallback={<TabFallback />}>
        {activeTab === 'catalog' ? (
          <CatalogGrid
            results={results}
            isLoading={isLoading}
            searchQuery={searchQuery}
            activeSource={activeSource}
            continueWatching={continueWatching}
            recentAnimes={recentAnimes}
            randomSuggestions={randomSuggestions}
            watchlist={watchlist}
            isInWatchlist={isInWatchlist}
            onToggleWatchlist={handleToggleWatchlist}
            onOpenWatchlist={() => setActiveTab('watchlist')}
            resumingKey={resumingKey}
            onRollRandom={loadRandomSuggestions}
            onSelectAnime={handleSelectAnime}
            onResumeEpisode={handleResumeEpisode}
          />
        ) : activeTab === 'history' ? (
          <HistoryView
            currentUser={currentUser}
            resumingKey={resumingKey}
            onSelectAnime={handleSelectAnime}
            onResumeEpisode={handleResumeEpisode}
          />
        ) : activeTab === 'watchlist' ? (
          // Remounted per profile: the ghosts of one profile must never be re-added to another
          <WatchlistView
            key={userId}
            currentUser={currentUser}
            watchlist={watchlist}
            continueWatching={continueWatching}
            isInWatchlist={isInWatchlist}
            resumingKey={resumingKey}
            onReload={loadWatchlist}
            onSelectAnime={handleSelectAnime}
            onToggleWatchlist={handleToggleWatchlist}
            onResumeEpisode={handleResumeEpisode}
          />
        ) : (
          <OfflineLibraryView
            onPlayEpisode={(title, season, ep, eps, cover, time, filePath, context) =>
              handlePlayEpisode(title, season, ep, eps, cover, time, filePath, context)
            }
          />
        )}
        </Suspense>
      </main>

      <Suspense fallback={null}>
      {selectedAnime && (
        <AnimeDetailModal
          currentUser={currentUser}
          anime={selectedAnime}
          onClose={handleCloseAnime}
          onPlayEpisode={(animeTitle, season, ep, eps, cover, time, filePath, context) => {
            handlePlayEpisode(animeTitle, season, ep, eps, cover, time, filePath, context);
            loadUserShelves();
          }}
          onDownloadEpisode={handleDownloadEpisode}
          onDownloadBulk={handleDownloadBulk}
          isInWatchlist={isInWatchlist}
          onToggleWatchlist={handleToggleWatchlist}
        />
      )}
      </Suspense>

      {/* Its own boundary: loading the player must never hide the anime page behind it */}
      <Suspense fallback={null}>
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
          context={activePlayer.context}
          autoResume={activePlayer.autoResume}
          fallbackPlayers={activePlayer.fallbackPlayers}
          onClose={(lastSave) => {
            resumeTokenRef.current += 1;
            setActivePlayer(null);
            // Once the player's last save is stored: the shelf then shows the final position
            Promise.resolve(lastSave).catch(() => {}).finally(loadUserShelves);
          }}
          onDownloadEpisode={handleDownloadEpisode}
          onSelectNextEpisode={(nextEp) => {
            // The context is kept: same anime, same season variant
            setActivePlayer((prev) => ({
              ...prev,
              episode: nextEp,
              initialTime: 0,
              initialFilePath: nextEp.file_path || null,
              autoResume: false,
              fallbackPlayers: null
            }));
          }}
        />
      )}
      </Suspense>

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

      {/* Above the detail modal (50), below the player (9999) */}
      {notice && (
        <div
          role="status"
          style={{
            position: 'fixed',
            left: '50%',
            bottom: 'calc(20px + env(safe-area-inset-bottom))',
            transform: 'translateX(-50%)',
            zIndex: 60,
            background: '#272727',
            border: '1px solid var(--border-active)',
            borderRadius: 'var(--radius-full)',
            padding: '8px 16px',
            fontSize: '0.85rem',
            color: '#fff',
            maxWidth: 'calc(100vw - 32px)',
            boxShadow: '0 8px 24px rgba(0,0,0,0.5)'
          }}
        >
          {notice}
        </div>
      )}
    </div>
  );
}
