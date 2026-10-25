import React, { useState, useEffect } from 'react';
import { X, Play, Download, Check, Loader2, CheckCircle2, RotateCw, HardDrive, BookOpen } from 'lucide-react';
import MangaReaderModal from './MangaReaderModal';
import { DEFAULT_ANIME_COVER } from '../utils/placeholders';

export default function AnimeDetailModal({
  currentUser,
  anime,
  onClose,
  onPlayEpisode,
  onDownloadEpisode,
  onDownloadBulk
}) {
  const [details, setDetails] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedSeason, setSelectedSeason] = useState(null);
  const [episodes, setEpisodes] = useState([]);
  const [isLoadingEpisodes, setIsLoadingEpisodes] = useState(false);
  const [history, setHistory] = useState({});
  const [downloadedEpisodes, setDownloadedEpisodes] = useState({}); // { "1": { file_path, size_mb } }
  const [downloadedScans, setDownloadedScans] = useState({}); // { "1": { downloaded: true } }
  const [readingChapter, setReadingChapter] = useState(null);
  const [downloadingScan, setDownloadingScan] = useState(null);

  const userId = currentUser?.id || 'default';

  // Fetch anime details & watch history for current user
  const loadAnimeDetails = (forceRefresh = false) => {
    if (!anime) return;
    setIsLoading(true);

    fetch('/api/history', {
      headers: { 'X-User-ID': userId }
    })
      .then((res) => res.json())
      .then((data) => setHistory(data || {}))
      .catch(() => {});

    fetch(`/api/details?url=${encodeURIComponent(anime.url)}&source=${anime.source}&refresh=${forceRefresh}`, {
      headers: { 'X-User-ID': userId }
    })
      .then((res) => res.json())
      .then((data) => {
        setDetails(data);
        if (data.seasons && data.seasons.length > 0) {
          const firstSeason = data.seasons[0];
          setSelectedSeason(firstSeason);
          loadSeasonEpisodes(firstSeason.url, firstSeason.name, forceRefresh);
        } else if (data.episodes) {
          setEpisodes(data.episodes);
          checkDownloadedStatus(data.title || anime.title, "Saison 1");
        }
      })
      .catch((err) => console.error("Error loading details:", err))
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    loadAnimeDetails(false);
  }, [anime, userId]);

  const loadSeasonEpisodes = (seasonUrl, seasonName = 'Saison 1', forceRefresh = false) => {
    setIsLoadingEpisodes(true);
    const targetTitle = details?.title || anime?.title || '';
    fetch(`/api/episodes?season_url=${encodeURIComponent(seasonUrl)}&anime_title=${encodeURIComponent(targetTitle)}&season_name=${encodeURIComponent(seasonName)}&refresh=${forceRefresh}`)
      .then((res) => res.json())
      .then((data) => {
        const eps = data.episodes || [];
        setEpisodes(eps);
        if (seasonName.toLowerCase() === 'scans' || data.is_scans) {
          checkScansStatus(targetTitle);
        } else {
          checkDownloadedStatus(targetTitle, seasonName);
        }
      })
      .catch((err) => console.error("Error loading episodes:", err))
      .finally(() => setIsLoadingEpisodes(false));
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

  const handleDownloadChapter = (chapNum) => {
    const title = details?.title || anime?.title;
    setDownloadingScan(chapNum);
    fetch('/api/scans/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ anime_title: title, chapter_num: Number(chapNum) })
    })
      .then((res) => res.json())
      .then(() => {
        checkScansStatus(title);
        setDownloadingScan(null);
      })
      .catch((err) => {
        console.error("Error downloading chapter:", err);
        setDownloadingScan(null);
      });
  };

  const handleDownloadAllScans = () => {
    const title = details?.title || anime?.title;
    setDownloadingScan('all');
    fetch('/api/scans/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ anime_title: title })
    })
      .then((res) => res.json())
      .then(() => {
        checkScansStatus(title);
        setDownloadingScan(null);
      })
      .catch((err) => {
        console.error("Error downloading all scans:", err);
        setDownloadingScan(null);
      });
  };

  const handleSeasonChange = (season) => {
    setSelectedSeason(season);
    loadSeasonEpisodes(season.url, season.name, false);
  };

  const isEpisodeWatched = (seasonName, epNum) => {
    const animeRecord = history[details?.title || anime?.title];
    if (!animeRecord || !animeRecord.episodes) return false;
    const epKey = `${seasonName}:${epNum}`;
    return animeRecord.episodes[epKey]?.watched || false;
  };

  const toggleEpisodeWatched = (seasonName, epNum, e) => {
    e.stopPropagation();
    const title = details?.title || anime?.title;
    fetch('/api/history/toggle-watched', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': userId
      },
      body: JSON.stringify({
        user_id: userId,
        anime_title: title,
        season: seasonName,
        ep_id: String(epNum)
      })
    })
      .then((res) => res.json())
      .then(() => {
        return fetch('/api/history', { headers: { 'X-User-ID': userId } }).then((res) => res.json());
      })
      .then((data) => setHistory(data || {}))
      .catch((err) => console.error("Error toggling watched:", err));
  };

  const handleMarkSeasonWatched = () => {
    const title = details?.title || anime?.title;
    const sName = selectedSeason?.name || 'Saison 1';
    const epIds = episodes.map((ep) => String(ep.num || ep.title || '1'));

    fetch('/api/history/mark-season', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': userId
      },
      body: JSON.stringify({
        user_id: userId,
        anime_title: title,
        season: sName,
        ep_ids: epIds,
        watched: true
      })
    })
      .then(() => fetch('/api/history', { headers: { 'X-User-ID': userId } }).then((res) => res.json()))
      .then((data) => setHistory(data || {}))
      .catch((err) => console.error("Error marking season:", err));
  };

  if (!anime) return null;

  const currentSeasonName = selectedSeason?.name || 'Saison 1';
  const animeTitle = details?.title || anime.title;
  // Real cover only: the placeholder must never be sent to the history as a cover
  const animeCover = details?.cover || anime.cover || '';
  const isScanMode = currentSeasonName?.toLowerCase() === 'scans' || (episodes.length > 0 && episodes[0]?.is_scan);

  return (
    <>
      <div style={{
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
          className="surface animate-fade-in"
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
          ) : (
            <div style={{ overflowY: 'auto', padding: '24px' }}>
              {/* Header Info */}
              <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
                <img
                  src={animeCover || DEFAULT_ANIME_COVER}
                  alt={animeTitle}
                  onError={(e) => {
                    e.target.src = DEFAULT_ANIME_COVER;
                  }}
                  style={{
                    width: '160px',
                    height: '230px',
                    objectFit: 'cover',
                    borderRadius: 'var(--radius-sm)',
                    boxShadow: '0 4px 16px rgba(0,0,0,0.4)'
                  }}
                />
                <div style={{ flex: 1, minWidth: '260px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className={`badge ${anime.source === 'anime_sama' ? 'badge-anime-sama' : 'badge-voiranime'}`}>
                      {anime.source === 'anime_sama' ? 'Anime-Sama' : 'VoirAnime'}
                    </span>
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: '0.72rem', padding: '2px 8px' }}
                      onClick={() => loadAnimeDetails(true)}
                      title="Actualiser le cache pour cet anime"
                    >
                      <RotateCw size={11} style={{ marginRight: '4px' }} /> Actualiser
                    </button>
                  </div>

                  <h2 style={{ fontSize: '1.6rem', fontWeight: 800 }}>{animeTitle}</h2>
                  {details?.synopsis && (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', lineHeight: '1.5', maxHeight: '90px', overflowY: 'auto' }}>
                      {details.synopsis}
                    </p>
                  )}

                  {/* Season Pills */}
                  {details?.seasons && details.seasons.length > 0 && (
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
                      {details.seasons.map((s, idx) => (
                        <button
                          key={idx}
                          className={`btn ${selectedSeason?.name === s.name ? 'btn-primary' : 'btn-secondary'}`}
                          style={{ padding: '4px 12px', fontSize: '0.8rem' }}
                          onClick={() => handleSeasonChange(s)}
                        >
                          {s.name}
                        </button>
                      ))}
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
                    <div style={{ display: 'flex', gap: '8px' }}>
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
                      ) : (
                        <>
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
                            onClick={() => onDownloadBulk(animeTitle, currentSeasonName, episodes)}
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
                    {isScanMode ? "Aucun chapitre de scan trouvé." : "Aucun épisode trouvé."}
                  </p>
                ) : (
                  <div style={{
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
                        const watched = isEpisodeWatched(currentSeasonName, epNum);
                        const localInfo = downloadedEpisodes[epNum];
                        const isDownloaded = Boolean(localInfo);

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
                              border: watched
                                ? '1px solid rgba(46, 160, 67, 0.4)'
                                : isDownloaded
                                ? '1px solid rgba(88, 166, 255, 0.3)'
                                : '1px solid var(--border-color)',
                              background: isDownloaded ? 'rgba(88, 166, 255, 0.04)' : undefined
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
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

                            <div style={{ display: 'flex', gap: '4px' }}>
                              <button
                                className="btn btn-primary"
                                style={{ flex: 1, padding: '4px 8px', fontSize: '0.78rem' }}
                                onClick={() => onPlayEpisode(
                                  animeTitle,
                                  currentSeasonName,
                                  ep,
                                  episodes,
                                  animeCover,
                                  0,
                                  localInfo?.file_path
                                )}
                              >
                                <Play size={12} fill="#fff" /> {isDownloaded ? "Lire Local" : "Lire"}
                              </button>
                              <button
                                className={`btn ${watched ? 'btn-success' : 'btn-secondary'}`}
                                style={{ padding: '4px 8px', fontSize: '0.78rem' }}
                                onClick={(e) => toggleEpisodeWatched(currentSeasonName, epNum, e)}
                                title={watched ? "Marquer non vu" : "Marquer vu"}
                              >
                                <Check size={14} />
                              </button>
                              <button
                                className={`btn btn-icon ${isDownloaded ? 'btn-success' : 'btn-secondary'}`}
                                style={{ width: '28px', height: '28px' }}
                                onClick={() => onDownloadEpisode(animeTitle, currentSeasonName, ep)}
                                title={isDownloaded ? "Déjà téléchargé sur le disque (Re-télécharger)" : "Télécharger sur le disque"}
                              >
                                <Download size={12} />
                              </button>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Fullscreen Manga Reader Modal */}
      {readingChapter !== null && (
        <MangaReaderModal
          mangaTitle={animeTitle}
          initialChapterNum={readingChapter}
          chapters={episodes}
          onClose={() => setReadingChapter(null)}
        />
      )}
    </>
  );
}
