import React, { useState, useEffect, useMemo, useRef } from 'react';
import { X, Play, Download, Check, Loader2, CheckCircle2, RotateCw, BookOpen, ShieldCheck, Smartphone } from 'lucide-react';
import MangaReaderModal from './MangaReaderModal';
import WatchlistButton from './WatchlistButton';
import { DEFAULT_ANIME_COVER, imageFallback } from '../utils/placeholders';
import { findHistoryEntries } from '../utils/titles';
import { animeRef, formatRelativeDate } from '../utils/animes';

const SOURCE_LABELS = { anime_sama: 'Anime-Sama', voiranime: 'VoirAnime' };
const VERSION_LABELS = { vostfr: 'VOSTFR', vf: 'VF' };

export default function AnimeDetailModal({
  currentUser,
  anime,
  onClose,
  onPlayEpisode,
  onDownloadEpisode,
  onDownloadBulk,
  onDownloadToDevice,
  isInWatchlist = () => false,
  onToggleWatchlist
}) {
  const [details, setDetails] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [selectedSeasonKey, setSelectedSeasonKey] = useState(null);
  const [activeVariant, setActiveVariant] = useState(null); // source + version actually served, with its season_key
  const seasonRequestRef = useRef(0); // only the latest season request may fill the list
  const [episodes, setEpisodes] = useState([]);
  const [isLoadingEpisodes, setIsLoadingEpisodes] = useState(false);
  const [history, setHistory] = useState({});
  const [downloadedEpisodes, setDownloadedEpisodes] = useState({}); // { "1": { file_path, size_mb } }
  const [downloadedScans, setDownloadedScans] = useState({}); // { "1": { downloaded: true } }
  const [readingChapter, setReadingChapter] = useState(null);
  const [downloadingScan, setDownloadingScan] = useState(null);
  const [synopsisOpen, setSynopsisOpen] = useState(false);
  // YoitsuWrap build of this anime: { state: none|queued|running|ready|expired|failed, built_at, ... }
  const [wrapperStatus, setWrapperStatus] = useState(null);
  // Episodes picked for a download to this device (selection mode of the episode grid)
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState(() => new Set());

  const userId = currentUser?.id || 'default';

  const refreshHistory = () =>
    fetch('/api/history', { headers: { 'X-User-ID': userId } })
      .then((res) => res.json())
      .then((data) => setHistory(data || {}))
      .catch(() => {});

  // Entity id of the clicked card; history/legacy links only know source + url + title
  const lookupEntityId = async () => {
    if (!anime?.url || !anime?.title) return null;
    // entry_title is the source entry's own title (what the lookup keys on), when the card knows it
    const params = new URLSearchParams({ source: anime.source || 'anime_sama', url: anime.url, title: anime.entry_title || anime.title });
    const res = await fetch(`/api/anime/lookup?${params}`);
    if (!res.ok) return null;
    return (await res.json()).id;
  };

  const fetchEntity = (entityId, forceRefresh) =>
    fetch(`/api/anime/${encodeURIComponent(entityId)}?refresh=${forceRefresh}`, { headers: { 'X-User-ID': userId } });

  const loadAnimeDetails = async (forceRefresh = false) => {
    if (!anime) return;
    setIsLoading(true);
    setLoadError('');
    refreshHistory();
    try {
      const cardId = anime.id && String(anime.id).startsWith('a-') ? anime.id : null;
      let res = cardId ? await fetchEntity(cardId, forceRefresh) : null;
      if (!res || res.status === 404) {
        // Ids of old cards can change when two entries are merged: find the entity again from its source entry
        const entityId = await lookupEntityId();
        if (!entityId) throw new Error('not found');
        res = await fetchEntity(entityId, forceRefresh);
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setDetails(data);
      const firstSeason = data.seasons?.find((s) => !s.is_scans) || data.seasons?.[0];
      if (firstSeason) {
        selectSeason(data, firstSeason, anime.source, 'vostfr', forceRefresh);
      } else {
        setEpisodes([]);
      }
    } catch (err) {
      console.error("Error loading details:", err);
      setLoadError("Impossible de charger cet anime.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAnimeDetails(false);
  }, [anime, userId]);

  // quiet: same season reloaded in place (YoitsuWrap links just became ready), no spinner
  const selectSeason = (data, season, source, version, forceRefresh = false, quiet = false) => {
    // A slow response of an earlier tap must not land under the tab clicked last
    const request = ++seasonRequestRef.current;
    const isLatest = () => request === seasonRequestRef.current;
    setSelectedSeasonKey(season.key);
    if (!quiet) {
      setIsLoadingEpisodes(true);
      setEpisodes([]);
      setWrapperStatus(null);
      setSelecting(false);
      setSelected(new Set());
    }

    if (season.is_scans) {
      // Manga scans keep using YoitsuWrap Scan objects through /api/episodes
      const variant = season.variants.find((v) => v.version === 'scans') || season.variants[0];
      setActiveVariant({ ...variant, season_key: season.key });
      fetch(`/api/episodes?season_url=${encodeURIComponent(variant.url)}&anime_title=${encodeURIComponent(variant.history_title)}&season_name=Scans&refresh=${forceRefresh}`)
        .then((res) => res.json())
        .then((res) => {
          if (!isLatest()) return;
          setEpisodes(res.episodes || []);
          checkScansStatus(variant.history_title);
        })
        .catch((err) => console.error("Error loading scans:", err))
        .finally(() => { if (isLatest()) setIsLoadingEpisodes(false); });
      return;
    }

    const params = new URLSearchParams({ season: season.key, source: source || '', version: version || 'vostfr', refresh: String(forceRefresh) });
    fetch(`/api/anime/${encodeURIComponent(data.id)}/episodes?${params}`)
      .then((res) => res.json())
      .then((res) => {
        if (!isLatest()) return;
        setEpisodes(res.episodes || []);
        // The season key travels with the variant of the same response: history writes pair them
        setActiveVariant(res.variant ? { ...res.variant, season_key: res.season?.key || season.key } : null);
        setWrapperStatus(res.wrapper || null);
        if (res.variant && !quiet) checkDownloadedStatus(res.variant.history_title, res.variant.season_name);
      })
      .catch((err) => console.error("Error loading episodes:", err))
      .finally(() => { if (isLatest()) setIsLoadingEpisodes(false); });
  };

  // While YoitsuWrap builds the anime (about a minute), check back; once ready, the list gets its verified links
  const wrapperState = wrapperStatus?.state;
  useEffect(() => {
    if (!details?.id || !activeVariant || !['queued', 'running'].includes(wrapperState)) return undefined;
    let cancelled = false;
    const timer = setTimeout(() => {
      fetch(`/api/anime/${encodeURIComponent(details.id)}/wrapper?version=${activeVariant.version}`)
        .then((res) => (res.ok ? res.json() : null))
        .then((status) => {
          if (cancelled || !status) return;
          const season = details.seasons?.find((s) => s.key === activeVariant.season_key);
          if (status.state === 'ready' && season) {
            selectSeason(details, season, activeVariant.source, activeVariant.version, false, true);
          } else {
            setWrapperStatus(status);
          }
        })
        .catch(() => {});
    }, 5000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [details, activeVariant, wrapperStatus]);

  const episodeKey = (ep, idx) => String(ep.num || ep.title || idx + 1);

  const toggleSelected = (key) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  // <folder>/<anime>/<season>/<version>/ep_<n>.mp4: every player of the episode is offered, best first
  const handleDeviceDownload = async () => {
    const season = details?.seasons?.find((s) => s.key === selectedSeasonKey);
    const items = episodes
      .map((ep, idx) => ({ ep, key: episodeKey(ep, idx) }))
      .filter(({ key }) => selected.has(key))
      .map(({ ep, key }) => ({
        anime: details?.title || anime?.title || 'Anime',
        season: season?.label || currentSeasonName,
        version: VERSION_LABELS[activeVariant?.version] || 'VOSTFR',
        num: key,
        urls: [...new Set([...(ep.players || []).map((p) => p.embed_url), ep.embed_url, ep.url].filter(Boolean))]
      }))
      .filter((item) => item.urls.length);
    if (!items.length) return;
    const started = await onDownloadToDevice?.(items);
    if (started) {
      setSelecting(false);
      setSelected(new Set());
    }
  };

  const checkDownloadedStatus = (title, seasonName) => {
    if (!title) return;
    fetch(`/api/episodes/download-status?anime_title=${encodeURIComponent(title)}&season=${encodeURIComponent(seasonName)}`)
      .then((res) => res.json())
      .then((data) => setDownloadedEpisodes(data.downloaded_episodes || {}))
      .catch(() => {});
  };

  const checkScansStatus = (title) => {
    if (!title) return;
    fetch(`/api/scans/status?anime_title=${encodeURIComponent(title)}`)
      .then((res) => res.json())
      .then((data) => setDownloadedScans(data.downloaded_chapters || {}))
      .catch(() => {});
  };

  // Titles under which progress/downloads of the active variant are stored (legacy keys included)
  const historyTitle = activeVariant?.history_title || details?.title || anime?.title || '';
  const currentSeasonName = activeVariant?.season_name || 'Saison 1';
  const historyEntries = useMemo(
    () => findHistoryEntries(history, activeVariant?.history_keys || [{ title: historyTitle, season: currentSeasonName }]),
    [history, activeVariant, historyTitle, currentSeasonName]
  );

  const handleDownloadChapter = (chapNum) => {
    setDownloadingScan(chapNum);
    fetch('/api/scans/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ anime_title: historyTitle, chapter_num: Number(chapNum) })
    })
      .then((res) => res.json())
      .then(() => {
        checkScansStatus(historyTitle);
        setDownloadingScan(null);
      })
      .catch((err) => {
        console.error("Error downloading chapter:", err);
        setDownloadingScan(null);
      });
  };

  const handleDownloadAllScans = () => {
    setDownloadingScan('all');
    fetch('/api/scans/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ anime_title: historyTitle })
    })
      .then((res) => res.json())
      .then(() => {
        checkScansStatus(historyTitle);
        setDownloadingScan(null);
      })
      .catch((err) => {
        console.error("Error downloading all scans:", err);
        setDownloadingScan(null);
      });
  };

  // Watched under any of the variant's keys (e.g. before the merge, under the VoirAnime post's own title)
  const watchedEntries = (epNum) =>
    historyEntries.filter(({ season, record }) => record.episodes?.[`${season}:${epNum}`]?.watched);
  const isEpisodeWatched = (epNum) => watchedEntries(epNum).length > 0;

  const setWatched = (title, season, epNum, watched, extra = {}) =>
    fetch('/api/history/toggle-watched', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': userId
      },
      body: JSON.stringify({ user_id: userId, anime_title: title, season, ep_id: String(epNum), watched, ...extra })
    });

  const toggleEpisodeWatched = (epNum, e) => {
    e.stopPropagation();
    const watchedIn = watchedEntries(epNum);
    // The following episode of this complete list: the server proposes it next on the home shelf
    const idx = episodes.findIndex((ep, i) => String(ep.num || ep.title || i + 1) === epNum);
    const next = idx >= 0 ? episodes[idx + 1] : null;
    const context = {
      anime: animeRef(details),
      season_key: activeVariant?.season_key,
      source: activeVariant?.source,
      version: activeVariant?.version,
      cover: animeCover,
      next_ep: next ? { ep_id: String(next.num || next.title || idx + 2), title: next.title || '' } : null
    };
    // Unwatching clears every record that marks it; watching writes under the current key
    const requests = watchedIn.length
      ? watchedIn.map(({ title, season }) => setWatched(title, season, epNum, false))
      : [setWatched(historyTitle, currentSeasonName, epNum, true, context)];
    Promise.all(requests)
      .then(() => refreshHistory())
      .catch((err) => console.error("Error toggling watched:", err));
  };

  const handleMarkSeasonWatched = () => {
    const epIds = episodes.map((ep) => String(ep.num || ep.title || '1'));
    fetch('/api/history/mark-season', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': userId
      },
      body: JSON.stringify({
        user_id: userId,
        anime_title: historyTitle,
        season: currentSeasonName,
        ep_ids: epIds,
        watched: true,
        anime: animeRef(details),
        season_key: activeVariant?.season_key,
        source: activeVariant?.source,
        version: activeVariant?.version,
        cover: animeCover
      })
    })
      .then(() => refreshHistory())
      .catch((err) => console.error("Error marking season:", err));
  };

  if (!anime) return null;

  const selectedSeason = details?.seasons?.find((s) => s.key === selectedSeasonKey) || null;
  const seasonVariants = selectedSeason?.variants || [];
  const seasonSources = [...new Set(seasonVariants.filter((v) => v.version !== 'scans').map((v) => v.source))];
  const versionOptions = ['vostfr', 'vf'].map((version) => {
    const candidates = seasonVariants.filter((v) => v.version === version);
    // Same source when it has this version, else a source known to have it, else an unverified one
    const preferred = candidates.find((v) => v.source === activeVariant?.source && v.available !== false)
      || candidates.find((v) => v.available === true)
      || candidates.find((v) => v.available !== false)
      || candidates[0];
    return { version, variant: preferred, available: candidates.some((v) => v.available !== false) };
  });
  const sourcesForVersion = seasonSources.filter((src) =>
    seasonVariants.some((v) => v.source === src && v.version === (activeVariant?.version || 'vostfr') && v.available !== false)
  );

  const animeTitle = details?.title || anime.title;
  // Real cover only: the placeholder must never be sent to the history as a cover
  const animeCover = details?.cover || anime.cover || '';
  const isScanMode = Boolean(selectedSeason?.is_scans) || (episodes.length > 0 && episodes[0]?.is_scan);
  const synopsis = details?.synopsis;
  const allSources = details?.sources?.length ? details.sources : [{ source: anime.source }];
  // What the player sends with its saves so the history record is linked to this entity and season variant
  const playContext = details && activeVariant && activeVariant.version !== 'scans' ? {
    anime: animeRef(details),
    seasonKey: activeVariant.season_key, // from the response that gave this variant, never the tab clicked last
    source: activeVariant.source,
    version: activeVariant.version,
    historyKeys: activeVariant.history_keys || [],
    via: 'player',
    fullSeason: true
  } : null;

  return (
    <>
      <div className="modal-overlay" style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        background: 'rgba(0, 0, 0, 0.85)',
        backdropFilter: 'blur(8px)'
      }} onClick={onClose}>
        <div
          className="surface animate-fade-in modal-sheet"
          onClick={(e) => e.stopPropagation()}
          style={{
            width: '100%',
            maxWidth: '880px',
            maxHeight: '90vh',
            borderRadius: 'var(--radius-md)',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            position: 'relative',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-color)'
          }}
        >
          {/* Close Button */}
          <button
            className="btn btn-icon btn-secondary"
            onClick={onClose}
            style={{
              position: 'absolute',
              top: '14px',
              right: '14px',
              zIndex: 10
            }}
          >
            <X size={18} />
          </button>

          {isLoading ? (
            <div style={{ padding: '80px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px' }}>
              <Loader2 className="animate-spin" size={28} color="var(--primary)" />
              <span>Chargement des informations de l'anime...</span>
            </div>
          ) : loadError ? (
            <div style={{ padding: '80px', textAlign: 'center', color: 'var(--text-muted)' }}>{loadError}</div>
          ) : (
            <div style={{ overflowY: 'auto' }}>
              {details?.banner && (
                <div style={{
                  height: '120px',
                  backgroundImage: `linear-gradient(to bottom, rgba(15,15,15,0.1), var(--bg-surface)), url("${details.banner}")`,
                  backgroundSize: 'cover',
                  backgroundPosition: 'center'
                }} />
              )}
              <div className="modal-body" style={{ padding: '24px', paddingTop: details?.banner ? '0' : '24px' }}>
              {/* Header Info */}
              <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
                <img
                  src={animeCover || DEFAULT_ANIME_COVER}
                  alt={animeTitle}
                  onError={imageFallback(details?.cover_fallbacks || [], DEFAULT_ANIME_COVER)}
                  className="detail-cover"
                  style={{
                    width: '160px',
                    height: '230px',
                    objectFit: 'cover',
                    borderRadius: 'var(--radius-sm)',
                    boxShadow: '0 4px 16px rgba(0,0,0,0.4)'
                  }}
                />
                <div style={{ flex: 1, minWidth: '260px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    {allSources.map((s) => (
                      <span key={s.source} className={`badge ${s.source === 'anime_sama' ? 'badge-anime-sama' : 'badge-voiranime'}`}>
                        {SOURCE_LABELS[s.source] || s.source}
                      </span>
                    ))}
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: '0.72rem', padding: '2px 8px' }}
                      onClick={() => loadAnimeDetails(true)}
                      title="Actualiser le cache pour cet anime"
                    >
                      <RotateCw size={11} style={{ marginRight: '4px' }} /> Actualiser
                    </button>
                  </div>

                  <div>
                    <h2 style={{ fontSize: '1.6rem', fontWeight: 800 }}>{animeTitle}</h2>
                    {details?.alt_titles?.length > 0 && (
                      <p style={{ color: 'var(--text-dim)', fontSize: '0.78rem', marginTop: '2px' }} title={details.alt_titles.join(' · ')}>
                        {details.alt_titles.slice(0, 3).join(' · ')}
                      </p>
                    )}
                  </div>

                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <WatchlistButton
                      variant="pill"
                      active={isInWatchlist(details || anime)}
                      onToggle={() => onToggleWatchlist(details || anime)}
                      disabled={!(details?.id || anime?.url)}
                    />
                  </div>

                  {details?.genres?.length > 0 && (
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      {details.genres.slice(0, 6).map((g) => (
                        <span key={g} className="badge" style={{ background: 'rgba(255,255,255,0.06)', color: 'var(--text-muted)' }}>{g}</span>
                      ))}
                    </div>
                  )}

                  {synopsis?.text && (
                    <div>
                      <p style={{
                        color: 'var(--text-muted)',
                        fontSize: '0.88rem',
                        lineHeight: '1.55',
                        whiteSpace: 'pre-line',
                        ...(synopsisOpen ? {} : { display: '-webkit-box', WebkitLineClamp: 4, WebkitBoxOrient: 'vertical', overflow: 'hidden' })
                      }}>
                        {synopsis.lang === 'en' && (
                          <span className="badge" style={{ marginRight: '6px', fontSize: '0.65rem' }} title="Synopsis en anglais (AniList)">EN</span>
                        )}
                        {synopsis.text}
                      </p>
                      {synopsis.text.length > 280 && (
                        <button
                          className="btn btn-ghost"
                          style={{ fontSize: '0.75rem', padding: '2px 8px', marginTop: '4px' }}
                          onClick={() => setSynopsisOpen((open) => !open)}
                        >
                          {synopsisOpen ? 'Réduire' : 'Lire la suite'}
                        </button>
                      )}
                    </div>
                  )}

                  {/* Season Pills */}
                  {details?.seasons?.length > 0 && (
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '4px' }}>
                      {details.seasons.map((s) => (
                        <button
                          key={s.key}
                          className={`btn ${selectedSeasonKey === s.key ? 'btn-primary' : 'btn-secondary'}`}
                          style={{ padding: '4px 12px', fontSize: '0.8rem' }}
                          onClick={() => selectSeason(details, s, activeVariant?.source, activeVariant?.version || 'vostfr')}
                        >
                          {s.label}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Links verified by YoitsuWrap: built once, rebuilt when they expire or with « Actualiser » */}
                  {selectedSeason && !isScanMode && wrapperState && wrapperState !== 'none' && (
                    <p style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.78rem', color: wrapperState === 'ready' ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                      {['queued', 'running'].includes(wrapperState) ? (
                        <span style={{ display: 'flex', flexDirection: 'column', gap: '5px', flex: 1, minWidth: 0 }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <Loader2 className="animate-spin" size={13} />
                            YoitsuWrap vérifie les liens{wrapperStatus.progress?.step ? ` · ${wrapperStatus.progress.step}` : '…'}
                            {wrapperStatus.progress ? ` (${Math.round(wrapperStatus.progress.value * 100)} %)` : ''}
                          </span>
                          <span className={`progress-track${wrapperStatus.progress ? '' : ' indeterminate'}`} style={{ maxWidth: '360px' }}>
                            <span style={{ display: 'block', height: '100%', background: 'var(--yt-red)', borderRadius: '2px', transition: 'width 0.4s ease', width: wrapperStatus.progress ? `${Math.max(3, wrapperStatus.progress.value * 100)}%` : undefined }} />
                          </span>
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Les lecteurs des sources restent disponibles en attendant.</span>
                        </span>
                      ) : wrapperState === 'ready' ? (
                        <><ShieldCheck size={14} /> Liens vérifiés par YoitsuWrap {formatRelativeDate(wrapperStatus.built_at).toLowerCase()}</>
                      ) : wrapperState === 'expired' ? (
                        <><RotateCw size={13} /> Liens YoitsuWrap expirés : nouvelle vérification au prochain chargement</>
                      ) : (
                        <>Vérification YoitsuWrap indisponible : lecteurs des sources utilisés</>
                      )}
                    </p>
                  )}

                  {/* Version & source selectors of the selected season */}
                  {selectedSeason && !isScanMode && (
                    <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', alignItems: 'center' }}>
                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Version</span>
                        {versionOptions.map(({ version, variant, available }) => (
                          <button
                            key={version}
                            className={`btn ${activeVariant?.version === version ? 'btn-primary' : 'btn-secondary'}`}
                            style={{ padding: '3px 10px', fontSize: '0.75rem', opacity: available ? 1 : 0.4 }}
                            disabled={!variant || !available}
                            title={!variant || !available ? 'Version indisponible' : variant.available === null ? 'Disponibilité non vérifiée' : ''}
                            onClick={() => selectSeason(details, selectedSeason, variant.source, version)}
                          >
                            {VERSION_LABELS[version]}{variant && variant.available === null ? ' ?' : ''}
                          </button>
                        ))}
                      </div>
                      {(sourcesForVersion.length > 1
                        || (sourcesForVersion.length > 0 && !sourcesForVersion.includes(activeVariant?.source))) && (
                        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Source</span>
                          {sourcesForVersion.map((src) => (
                            <button
                              key={src}
                              className={`btn ${activeVariant?.source === src ? 'btn-primary' : 'btn-secondary'}`}
                              style={{ padding: '3px 10px', fontSize: '0.75rem' }}
                              onClick={() => selectSeason(details, selectedSeason, src, activeVariant?.version || 'vostfr')}
                            >
                              {SOURCE_LABELS[src] || src}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Episode or Scans List Section */}
              <div style={{ marginTop: '28px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
                  <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>
                    {isScanMode ? `📖 Chapitres Scans (${episodes.length})` : `Épisodes (${episodes.length})`}
                  </h3>
                  {episodes.length > 0 && (
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      {isScanMode ? (
                        <button
                          className="btn btn-secondary"
                          style={{ fontSize: '0.78rem', padding: '4px 10px' }}
                          onClick={handleDownloadAllScans}
                          disabled={downloadingScan === 'all'}
                        >
                          {downloadingScan === 'all' ? (
                            <Loader2 className="animate-spin" size={14} style={{ marginRight: '4px' }} />
                          ) : (
                            <Download size={14} style={{ marginRight: '4px' }} />
                          )}
                          Tout Télécharger les Scans
                        </button>
                      ) : selecting ? (
                        <>
                          <button
                            className="btn btn-secondary"
                            style={{ fontSize: '0.78rem', padding: '4px 10px' }}
                            onClick={() => setSelected(selected.size === episodes.length
                              ? new Set()
                              : new Set(episodes.map((ep, idx) => episodeKey(ep, idx))))}
                          >
                            {selected.size === episodes.length ? 'Tout désélectionner' : 'Tout sélectionner'}
                          </button>
                          <button className="btn btn-secondary" style={{ fontSize: '0.78rem', padding: '4px 10px' }} onClick={() => setSelecting(false)}>
                            Annuler
                          </button>
                          <button
                            className="btn btn-primary"
                            style={{ fontSize: '0.78rem', padding: '4px 12px' }}
                            onClick={handleDeviceDownload}
                            disabled={!selected.size}
                          >
                            <Smartphone size={14} /> Télécharger sur cet appareil ({selected.size})
                          </button>
                        </>
                      ) : (
                        <>
                          {onDownloadToDevice && (
                            <button
                              className="btn btn-secondary"
                              style={{ fontSize: '0.78rem', padding: '4px 10px' }}
                              onClick={() => setSelecting(true)}
                              title="Choisir des épisodes à enregistrer sur cet appareil (téléphone, PC)"
                            >
                              <Smartphone size={14} /> Sur cet appareil
                            </button>
                          )}
                          <button
                            className="btn btn-secondary"
                            style={{ fontSize: '0.78rem', padding: '4px 10px' }}
                            onClick={handleMarkSeasonWatched}
                          >
                            <CheckCircle2 size={14} color="var(--accent-green)" /> Tout marquer vu
                          </button>
                          <button
                            className="btn btn-secondary"
                            style={{ fontSize: '0.78rem', padding: '4px 10px' }}
                            onClick={() => onDownloadBulk(historyTitle, currentSeasonName, episodes)}
                          >
                            <Download size={14} /> Tout Télécharger
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </div>

                {isLoadingEpisodes ? (
                  <div style={{ padding: '40px', textAlign: 'center' }}>
                    <Loader2 className="animate-spin" size={24} color="var(--primary)" />
                  </div>
                ) : episodes.length === 0 ? (
                  <p style={{ color: 'var(--text-muted)' }}>
                    {isScanMode
                      ? "Aucun chapitre de scan trouvé."
                      : activeVariant?.version === 'vf'
                        ? "Aucun épisode trouvé en VF pour cette source."
                        : "Aucun épisode trouvé."}
                  </p>
                ) : (
                  <div className="episode-grid" style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
                    gap: '10px',
                    maxHeight: '340px',
                    overflowY: 'auto'
                  }}>
                    {isScanMode ? (
                      episodes.map((ep, idx) => {
                        const chapNum = String(ep.num || idx + 1);
                        const localInfo = downloadedScans[chapNum];
                        const isDownloaded = Boolean(localInfo);
                        const isDownloadingThis = downloadingScan === ep.num || downloadingScan === 'all';

                        return (
                          <div
                            key={idx}
                            className="surface-card"
                            style={{
                              padding: '10px 12px',
                              borderRadius: 'var(--radius-sm)',
                              display: 'flex',
                              flexDirection: 'column',
                              gap: '8px',
                              border: isDownloaded
                                ? '1px solid rgba(88, 166, 255, 0.4)'
                                : '1px solid var(--border-color)',
                              background: isDownloaded ? 'rgba(88, 166, 255, 0.05)' : undefined
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <span style={{ fontSize: '0.88rem', fontWeight: 600, color: '#fff' }}>
                                {ep.title || `Chapitre ${chapNum}`}
                              </span>
                              <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                                {ep.pages_count && (
                                  <span className="badge" style={{ fontSize: '0.68rem', padding: '2px 5px', background: 'rgba(255,255,255,0.08)' }}>
                                    {ep.pages_count} pages
                                  </span>
                                )}
                                {isDownloaded && (
                                  <span className="badge" style={{ background: 'rgba(56, 139, 253, 0.2)', color: '#58A6FF', fontSize: '0.68rem', padding: '2px 5px' }} title="Disponible localement">
                                    💾 Local
                                  </span>
                                )}
                              </div>
                            </div>

                            <div style={{ display: 'flex', gap: '6px' }}>
                              <button
                                className="btn btn-primary"
                                style={{ flex: 1, padding: '5px 8px', fontSize: '0.78rem' }}
                                onClick={() => setReadingChapter(ep.num)}
                              >
                                <BookOpen size={13} style={{ marginRight: '4px' }} /> Lire le Chapitre
                              </button>
                              <button
                                className={`btn btn-icon ${isDownloaded ? 'btn-success' : 'btn-secondary'}`}
                                style={{ width: '30px', height: '30px' }}
                                onClick={() => handleDownloadChapter(ep.num)}
                                disabled={isDownloadingThis}
                                title={isDownloaded ? "Chapitre déjà téléchargé (Re-télécharger)" : "Télécharger ce chapitre"}
                              >
                                {isDownloadingThis ? (
                                  <Loader2 className="animate-spin" size={13} />
                                ) : (
                                  <Download size={13} />
                                )}
                              </button>
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      episodes.map((ep, idx) => {
                        const epNum = String(ep.num || ep.title || idx + 1);
                        const watched = isEpisodeWatched(epNum);
                        const localInfo = downloadedEpisodes[epNum];
                        const isDownloaded = Boolean(localInfo);
                        const isPicked = selecting && selected.has(episodeKey(ep, idx));

                        return (
                          <div
                            key={idx}
                            className="surface-card"
                            role={selecting ? 'checkbox' : undefined}
                            aria-checked={selecting ? isPicked : undefined}
                            tabIndex={selecting ? 0 : undefined}
                            onClick={selecting ? () => toggleSelected(episodeKey(ep, idx)) : undefined}
                            onKeyDown={selecting ? (e) => {
                              if (e.key === ' ' || e.key === 'Enter') {
                                e.preventDefault();
                                toggleSelected(episodeKey(ep, idx));
                              }
                            } : undefined}
                            style={{
                              position: 'relative',
                              cursor: selecting ? 'pointer' : undefined,
                              padding: '10px 12px',
                              borderRadius: 'var(--radius-sm)',
                              display: 'flex',
                              flexDirection: 'column',
                              gap: '8px',
                              border: isPicked
                                ? '1px solid var(--primary)'
                                : watched
                                ? '1px solid rgba(46, 160, 67, 0.4)'
                                : isDownloaded
                                ? '1px solid rgba(88, 166, 255, 0.3)'
                                : '1px solid var(--border-color)',
                              background: isDownloaded ? 'rgba(88, 166, 255, 0.04)' : undefined
                            }}
                          >
                            {selecting && (
                              <input type="checkbox" className="episode-select" checked={isPicked} readOnly tabIndex={-1} aria-hidden="true" />
                            )}
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingRight: selecting ? '28px' : 0 }}>
                              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: watched ? '#3FB950' : '#fff' }}>
                                {ep.title || `Épisode ${epNum}`}
                              </span>
                              <div style={{ display: 'flex', gap: '4px' }}>
                                {isDownloaded && (
                                  <span className="badge" style={{ background: 'rgba(56, 139, 253, 0.2)', color: '#58A6FF', fontSize: '0.68rem', padding: '2px 5px' }} title="Fichier disponible sur le disque">
                                    💾 Local
                                  </span>
                                )}
                                {watched && (
                                  <span className="badge badge-watched" style={{ fontSize: '0.68rem', padding: '2px 5px' }}>✓ Vu</span>
                                )}
                              </div>
                            </div>

                            {!selecting && <div style={{ display: 'flex', gap: '4px' }}>
                              <button
                                className="btn btn-primary"
                                style={{ flex: 1, padding: '4px 8px', fontSize: '0.78rem' }}
                                onClick={() => onPlayEpisode(
                                  historyTitle,
                                  currentSeasonName,
                                  ep,
                                  episodes,
                                  animeCover,
                                  0,
                                  localInfo?.file_path,
                                  playContext
                                )}
                              >
                                <Play size={12} fill="#fff" /> {isDownloaded ? "Lire Local" : "Lire"}
                              </button>
                              <button
                                className={`btn ${watched ? 'btn-success' : 'btn-secondary'}`}
                                style={{ padding: '4px 8px', fontSize: '0.78rem' }}
                                onClick={(e) => toggleEpisodeWatched(epNum, e)}
                                title={watched ? "Marquer non vu" : "Marquer vu"}
                              >
                                <Check size={14} />
                              </button>
                              <button
                                className={`btn btn-icon ${isDownloaded ? 'btn-success' : 'btn-secondary'}`}
                                style={{ width: '28px', height: '28px' }}
                                onClick={() => onDownloadEpisode(historyTitle, currentSeasonName, ep)}
                                title={isDownloaded ? "Déjà téléchargé sur le disque (Re-télécharger)" : "Télécharger sur le disque"}
                              >
                                <Download size={12} />
                              </button>
                            </div>}
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Fullscreen Manga Reader Modal */}
      {readingChapter !== null && (
        <MangaReaderModal
          mangaTitle={historyTitle}
          initialChapterNum={readingChapter}
          chapters={episodes}
          onClose={() => setReadingChapter(null)}
        />
      )}
    </>
  );
}
