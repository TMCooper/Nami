import React, { useState, useEffect, useMemo, useRef } from 'react';
import { X, Play, Download, Check, Loader2, CheckCircle2, RotateCw, BookOpen, ShieldCheck, Smartphone, Layers } from 'lucide-react';
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
  onDownloadsStarted,
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
  // The fiche YoitsuWrap builds (seasons, episodes and their source): what the page shows once ready
  const [fiche, setFiche] = useState(null);
  const [version, setVersion] = useState('vostfr');
  // « Voir les épisodes des sources sans attendre »: the source APIs' seasons instead of the fiche
  const [sourcesMode, setSourcesMode] = useState(false);
  const [notice, setNotice] = useState('');
  // What YoitsuWrap said about the season shown (links the API gave, failed call, another season's episodes)
  const [seasonInfo, setSeasonInfo] = useState(null);
  const ficheRequestRef = useRef(0);
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
      setSourcesMode(false);
      setNotice('');
      setEpisodes([]);
      setSelectedSeasonKey(null);
      loadFiche(data, forceRefresh ? version : 'vostfr', forceRefresh, forceRefresh ? selectedSeasonKey : null);
    } catch (err) {
      console.error("Error loading details:", err);
      setLoadError("Impossible de charger cet anime.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    setFiche(null);
    setVersion('vostfr');
    loadAnimeDetails(false);
  }, [anime, userId]);

  const firstSeasonOf = (list) => list?.find((s) => !s.is_scans) || list?.[0] || null;
  // A fiche without any episode (no VF, say) is no fiche: its scans alone would hide that
  const hasEpisodes = (next) => Boolean(next?.fiche?.seasons?.some((s) => !s.is_scans && s.episodes > 0));

  // The fiche of a version: starts its build when needed; its seasons are shown once it exists
  const loadFiche = (data, v, refresh = false, keepSeasonKey = null) => {
    const request = ++ficheRequestRef.current;
    setVersion(v);
    return fetch(`/api/anime/${encodeURIComponent(data.id)}/fiche?version=${v}&refresh=${refresh}`)
      .then((res) => (res.ok ? res.json() : { state: 'failed', error: `HTTP ${res.status}`, fiche: null }))
      .catch(() => ({ state: 'failed', error: 'Serveur injoignable', fiche: null }))
      .then((next) => {
        if (request !== ficheRequestRef.current) return;
        setFiche(next);
        const seasons = next.fiche?.seasons;
        if (hasEpisodes(next)) {
          const season = seasons.find((s) => s.key === keepSeasonKey) || firstSeasonOf(seasons);
          selectSeason(data, season, '', v);
        } else {
          setEpisodes([]);
          setSelectedSeasonKey(null);
        }
      });
  };
  // quiet: same season reloaded in place (YoitsuWrap links just became ready), no spinner
  const selectSeason = (data, season, source, version, forceRefresh = false, quiet = false) => {
    // A slow response of an earlier tap must not land under the tab clicked last
    const request = ++seasonRequestRef.current;
    const isLatest = () => request === seasonRequestRef.current;
    setSelectedSeasonKey(season.key);
    if (!quiet) {
      setIsLoadingEpisodes(true);
      setEpisodes([]);
      setSelecting(false);
      setSelected(new Set());
    }

    if (season.is_scans) {
      // Manga scans keep using YoitsuWrap Scan objects through /api/episodes
      const variants = (data.seasons?.find((s) => s.key === season.key) || season).variants || [];
      const variant = variants.find((v) => v.version === 'scans') || variants[0];
      if (!variant) {
        setEpisodes([]);
        setIsLoadingEpisodes(false);
        return;
      }
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
        setSeasonInfo(res.from_wrapper ? res.season : null);
        if (res.variant && !quiet) checkDownloadedStatus(res.variant, res.season?.label, version || 'vostfr');
      })
      .catch((err) => console.error("Error loading episodes:", err))
      .finally(() => { if (isLatest()) setIsLoadingEpisodes(false); });
  };

  // While YoitsuWrap builds the fiche, check back; the page shows it as soon as it exists
  const ficheState = fiche?.state;
  useEffect(() => {
    if (!details?.id || !['queued', 'running'].includes(ficheState)) return undefined;
    let cancelled = false;
    const timer = setTimeout(() => {
      const request = ficheRequestRef.current;
      fetch(`/api/anime/${encodeURIComponent(details.id)}/fiche?version=${version}`)
        .then((res) => (res.ok ? res.json() : null))
        .then((next) => {
          if (cancelled || !next || request !== ficheRequestRef.current) return;
          const hadFiche = hasEpisodes(fiche);
          setFiche(next);
          if (!hasEpisodes(next) || sourcesMode) return;
          if (!hadFiche) {
            selectSeason(details, firstSeasonOf(next.fiche.seasons), '', version);
          } else if (next.state === 'ready') {
            // Rebuilt: the same season again, with the new links
            const season = next.fiche.seasons.find((s) => s.key === selectedSeasonKey) || firstSeasonOf(next.fiche.seasons);
            selectSeason(details, season, '', version, false, season.key === selectedSeasonKey);
          }
        })
        .catch(() => {});
    }, 3000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [details, fiche, version, sourcesMode, selectedSeasonKey]);

  const showSources = () => {
    setSourcesMode(true);
    const season = firstSeasonOf(details?.seasons);
    if (season) selectSeason(details, season, anime?.source, version);
  };

  // Back to the fiche of this version, else to the VOSTFR one (no VF fiche)
  const backToFiche = () => {
    setSourcesMode(false);
    loadFiche(details, hasEpisodes(fiche) ? version : 'vostfr');
  };

  const episodeKey = (ep, idx) => String(ep.num || ep.title || idx + 1);

  const toggleSelected = (key) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  const ficheDownload = (nums) => ({ animeId: details?.id, season: selectedSeasonKey, version, episodes: nums });

  // YoitsuWrap prepares the episodes on the server, the page copies them here as they are ready
  const handleDeviceDownload = async () => {
    const nums = episodes
      .map((ep, idx) => ({ ep, key: episodeKey(ep, idx) }))
      .filter(({ key }) => selected.has(key))
      .map(({ ep }) => Number(ep.num))
      .filter((n) => Number.isFinite(n));
    if (!nums.length) return;
    const result = await onDownloadToDevice?.(ficheDownload(nums));
    if (result?.ok) {
      setSelecting(false);
      setSelected(new Set());
      setNotice('');
    } else if (result?.error) {
      setNotice(result.error);
    }
  };

  // Into the server's library, by YoitsuWrap (episodes in parallel, progress in the downloads drawer)
  const downloadOnServer = async (nums) => {
    setNotice('');
    const res = await fetch('/api/downloads/fiche', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ anime_id: details?.id, season: selectedSeasonKey, version, episodes: nums })
    }).catch(() => null);
    const data = res ? await res.json().catch(() => ({})) : {};
    if (res?.ok) onDownloadsStarted?.();
    else setNotice(data.detail || 'Téléchargement impossible pour le moment.');
  };

  // Files of this season on the server: old downloads (history title + season name) and YoitsuWrap's (fiche title + season + version)
  const checkDownloadedStatus = (variant, label, v) => {
    if (!variant?.history_title) return;
    const params = new URLSearchParams({ season: variant.season_name || 'Saison 1', label: label || '', version: v });
    [...new Set([variant.history_title, fiche?.fiche?.title, details?.title].filter(Boolean))]
      .forEach((t) => params.append('anime_title', t));
    fetch(`/api/episodes/download-status?${params}`)
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

  const ficheData = fiche?.fiche || null;
  // The fiche's seasons once it exists; the source APIs' ones only when asked for
  const fromFiche = hasEpisodes(fiche) && !sourcesMode;
  const seasonList = fromFiche ? ficheData.seasons : sourcesMode ? (details?.seasons || []) : [];
  const waitingForFiche = !fromFiche && !sourcesMode && Boolean(details);
  const selectedSeason = seasonList.find((s) => s.key === selectedSeasonKey) || null;
  const sourceSeason = details?.seasons?.find((s) => s.key === selectedSeasonKey) || null;
  const seasonVariants = sourceSeason?.variants || [];
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

  const animeTitle = ficheData?.title || details?.title || anime.title;
  // Real cover only: the placeholder must never be sent to the history as a cover
  const animeCover = ficheData?.cover || details?.cover || anime.cover || '';
  const isScanMode = Boolean(selectedSeason?.is_scans) || (episodes.length > 0 && episodes[0]?.is_scan);
  const synopsis = ficheData?.synopsis || details?.synopsis;
  const allSources = ficheData?.sources?.length
    ? ficheData.sources.map((source) => ({ source }))
    : details?.sources?.length ? details.sources : [{ source: anime.source }];
  const ficheProgress = fiche?.progress;
  const ficheBusy = ['queued', 'running'].includes(ficheState);
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
              {animeCover && (
                <div className="detail-backdrop" aria-hidden="true">
                  <div style={{ backgroundImage: `url("${animeCover}")` }} />
                </div>
              )}
              <div className="modal-body" style={{ padding: '24px', paddingTop: animeCover ? '0' : '24px', position: 'relative' }}>
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
                      disabled={ficheBusy}
                      title="Reconstruire la fiche avec YoitsuWrap (liens et épisodes à jour)"
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

                  {/* Version of the fiche (each one is its own YoitsuWrap build) */}
                  {!sourcesMode && details && (
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Version</span>
                      {['vostfr', 'vf'].map((v) => (
                        <button
                          key={v}
                          className={`btn ${version === v ? 'btn-primary' : 'btn-secondary'}`}
                          style={{ padding: '3px 10px', fontSize: '0.75rem' }}
                          onClick={() => version !== v && loadFiche(details, v)}
                        >
                          {VERSION_LABELS[v]}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Season Pills */}
                  {seasonList.length > 0 && (
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '4px' }}>
                      {seasonList.map((s) => (
                        <button
                          key={s.key}
                          className={`btn ${selectedSeasonKey === s.key ? 'btn-primary' : 'btn-secondary'}`}
                          style={{ padding: '4px 12px', fontSize: '0.8rem', opacity: fromFiche && !s.is_scans && !s.episodes ? 0.55 : 1 }}
                          title={fromFiche && !s.is_scans
                            ? (s.episodes ? `${s.episodes} épisode${s.episodes > 1 ? 's' : ''}` : 'Aucun épisode gardé par YoitsuWrap')
                            : undefined}
                          onClick={() => selectSeason(details, s, sourcesMode ? activeVariant?.source : '', fromFiche ? version : activeVariant?.version || 'vostfr')}
                        >
                          {s.label}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* State of the fiche: built by YoitsuWrap, rebuilt when its links expire or with « Actualiser » */}
                  {fromFiche && (
                    <p className="fiche-status" style={{ color: ficheState === 'ready' ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                      {ficheBusy ? (
                        <span style={{ display: 'flex', flexDirection: 'column', gap: '5px', flex: 1, minWidth: 0 }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <Loader2 className="animate-spin" size={13} />
                            YoitsuWrap met la fiche à jour{ficheProgress?.step ? ` · ${ficheProgress.step}` : '…'}
                            {ficheProgress ? ` (${Math.round(ficheProgress.value * 100)} %)` : ''}
                          </span>
                          <span className={`progress-track${ficheProgress ? '' : ' indeterminate'}`} style={{ maxWidth: '360px' }}>
                            <div style={{ width: ficheProgress ? `${Math.max(3, ficheProgress.value * 100)}%` : undefined }} />
                          </span>
                        </span>
                      ) : ficheState === 'ready' ? (
                        <><ShieldCheck size={14} /> Fiche YoitsuWrap · liens vérifiés {formatRelativeDate(fiche.built_at).toLowerCase()}</>
                      ) : (
                        <><RotateCw size={13} /> {fiche?.error
                          ? `Mise à jour de la fiche impossible (${fiche.error}) : « Actualiser » pour réessayer`
                          : 'Liens de la fiche expirés : « Actualiser » les vérifie à nouveau'}</>
                      )}
                    </p>
                  )}
                  {sourcesMode && (
                    <p className="fiche-status" style={{ color: 'var(--text-muted)' }}>
                      <Layers size={14} /> Épisodes des sources, sans la vérification de YoitsuWrap
                      <button className="btn btn-ghost" style={{ fontSize: '0.75rem', padding: '2px 8px' }} onClick={backToFiche}>Revenir à la fiche YoitsuWrap</button>
                    </p>
                  )}

                  {/* Version & source selectors of the source APIs' season */}
                  {sourcesMode && selectedSeason && !isScanMode && (
                    <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', alignItems: 'center' }}>
                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Version</span>
                        {versionOptions.map(({ version: v, variant, available }) => (
                          <button
                            key={v}
                            className={`btn ${activeVariant?.version === v ? 'btn-primary' : 'btn-secondary'}`}
                            style={{ padding: '3px 10px', fontSize: '0.75rem', opacity: available ? 1 : 0.4 }}
                            disabled={!variant || !available}
                            title={!variant || !available ? 'Version indisponible' : variant.available === null ? 'Disponibilité non vérifiée' : ''}
                            onClick={() => selectSeason(details, selectedSeason, variant.source, v)}
                          >
                            {VERSION_LABELS[v]}{variant && variant.available === null ? ' ?' : ''}
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

              {/* YoitsuWrap builds the fiche: the page waits for it rather than guess seasons from the sources */}
              {waitingForFiche && (
                <div className="fiche-wait" role="status" aria-live="polite">
                  {fiche === null || ficheBusy ? (
                    <>
                      <div className="fiche-wait-spinner" aria-hidden="true"><span /><span /><span /></div>
                      <h3>{fiche?.state === 'queued' ? 'Fiche en file d\'attente' : 'YoitsuWrap prépare la fiche de cet anime'}</h3>
                      <p>
                        {fiche?.state === 'queued'
                          ? 'Une autre fiche est en cours de préparation : celle-ci suit juste après.'
                          : `Il rassemble les saisons d'Anime-Sama et de VoirAnime sans doublon et vérifie chaque lien (${VERSION_LABELS[version]}). Une seule fois : ensuite la fiche s'ouvre directement.`}
                      </p>
                      <div className={`progress-track${ficheProgress ? '' : ' indeterminate'}`} style={{ width: '100%', maxWidth: '420px' }}>
                        <div style={{ width: ficheProgress ? `${Math.max(3, ficheProgress.value * 100)}%` : undefined }} />
                      </div>
                      <span className="fiche-wait-step">
                        {ficheProgress ? `${ficheProgress.step} · ${Math.round(ficheProgress.value * 100)} %` : 'Démarrage…'}
                      </span>
                    </>
                  ) : (
                    <>
                      <h3>{version === 'vf' ? 'Pas de fiche VF' : 'Fiche indisponible'}</h3>
                      <p>
                        {version === 'vf'
                          ? "YoitsuWrap n'a pas trouvé cet anime en VF."
                          : ficheData
                            ? "YoitsuWrap n'a trouvé aucun épisode pour cet anime."
                            : `YoitsuWrap n'a pas pu construire la fiche${fiche?.error ? ` : ${fiche.error}` : '.'}`}
                      </p>
                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center' }}>
                        {version === 'vf' ? (
                          <button className="btn btn-primary" onClick={() => loadFiche(details, 'vostfr')}>Revenir en VOSTFR</button>
                        ) : fiche?.state !== 'unavailable' && (
                          <button className="btn btn-primary" onClick={() => loadFiche(details, version, true)}>
                            <RotateCw size={14} /> Réessayer
                          </button>
                        )}
                      </div>
                    </>
                  )}
                  {details?.seasons?.some((s) => !s.is_scans) && (
                    <button className="btn btn-ghost" style={{ fontSize: '0.78rem' }} onClick={showSources}>
                      Voir les épisodes des sources sans attendre
                    </button>
                  )}
                </div>
              )}

              {notice && (
                <p className="fiche-notice" role="alert">{notice}</p>
              )}

              {/* Episode or Scans List Section */}
              {selectedSeason && <div style={{ marginTop: '28px' }}>
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
                          {onDownloadToDevice && fromFiche && (
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
                            onClick={() => (fromFiche ? downloadOnServer([]) : onDownloadBulk(historyTitle, currentSeasonName, episodes))}
                            title={fromFiche ? 'Toute la saison sur le serveur, par YoitsuWrap (épisodes en parallèle)' : undefined}
                          >
                            <Download size={14} /> Tout Télécharger
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </div>

                {!isLoadingEpisodes && fromFiche && seasonInfo && !isScanMode && (seasonInfo.same_as || !episodes.some((ep) => ep.verified)) && (
                  <p className="fiche-season-note">
                    {seasonInfo.same_as
                      ? `L'API a renvoyé les mêmes épisodes que « ${seasonInfo.same_as} » pour cette saison : YoitsuWrap les a gardés tels quels.`
                      : `YoitsuWrap n'a gardé aucun épisode de cette saison : ${seasonInfo.error
                        ? `${seasonInfo.error}.`
                        : seasonInfo.api_links
                          ? `l'API a donné ${seasonInfo.api_links} lien${seasonInfo.api_links > 1 ? 's' : ''}, aucun n'a passé la vérification.`
                          : "l'API n'a renvoyé aucun lien."}${episodes.length ? ' Les épisodes de la source sont listés ci-dessous, sans vérification.' : ' « Actualiser » relance la fiche.'}`}
                  </p>
                )}

                {isLoadingEpisodes ? (
                  <div style={{ padding: '40px', textAlign: 'center' }}>
                    <Loader2 className="animate-spin" size={24} color="var(--primary)" />
                  </div>
                ) : episodes.length === 0 ? (fromFiche && seasonInfo && !isScanMode ? null :
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
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '4px', paddingRight: selecting ? '28px' : 0 }}>
                              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: watched ? '#3FB950' : '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '100%' }} title={ep.title || `Épisode ${epNum}`}>
                                {ep.title || `Épisode ${epNum}`}
                              </span>
                              <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
                                {(ep.source || activeVariant?.source) && (
                                  <span
                                    className={`badge ep-source ${(ep.source || activeVariant?.source) === 'anime_sama' ? 'badge-anime-sama' : 'badge-voiranime'}${ep.verified === false ? ' unverified' : ''}`}
                                    title={ep.verified === false ? 'Lien non vérifié par YoitsuWrap' : `Épisode pris sur ${SOURCE_LABELS[ep.source || activeVariant?.source]}`}
                                  >
                                    {SOURCE_LABELS[ep.source || activeVariant?.source] || ep.source}
                                  </span>
                                )}
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
                                onClick={() => (fromFiche ? downloadOnServer([Number(ep.num)]) : onDownloadEpisode(historyTitle, currentSeasonName, ep))}
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
              </div>}
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
