import React, { useState, useEffect } from 'react';
import { X, Play, Download, Check, Loader2, CheckCircle2 } from 'lucide-react';

export default function AnimeDetailModal({ anime, onClose, onPlayEpisode, onDownloadEpisode, onDownloadBulk }) {
  const [details, setDetails] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedSeason, setSelectedSeason] = useState(null);
  const [episodes, setEpisodes] = useState([]);
  const [isLoadingEpisodes, setIsLoadingEpisodes] = useState(false);
  const [history, setHistory] = useState({});

  // Fetch anime details & watch history
  useEffect(() => {
    if (!anime) return;
    setIsLoading(true);

    fetch('/api/history')
      .then((res) => res.json())
      .then((data) => setHistory(data || {}))
      .catch(() => {});

    fetch(`/api/details?url=${encodeURIComponent(anime.url)}&source=${anime.source}`)
      .then((res) => res.json())
      .then((data) => {
        setDetails(data);
        if (data.seasons && data.seasons.length > 0) {
          setSelectedSeason(data.seasons[0]);
          loadSeasonEpisodes(data.seasons[0].url);
        } else if (data.episodes) {
          setEpisodes(data.episodes);
        }
      })
      .catch((err) => console.error("Error loading details:", err))
      .finally(() => setIsLoading(false));
  }, [anime]);

  const loadSeasonEpisodes = (seasonUrl) => {
    setIsLoadingEpisodes(true);
    fetch(`/api/episodes?season_url=${encodeURIComponent(seasonUrl)}`)
      .then((res) => res.json())
      .then((data) => {
        setEpisodes(data.episodes || []);
      })
      .catch((err) => console.error("Error loading episodes:", err))
      .finally(() => setIsLoadingEpisodes(false));
  };

  const handleSeasonChange = (season) => {
    setSelectedSeason(season);
    loadSeasonEpisodes(season.url);
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
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        anime_title: title,
        season: seasonName,
        ep_id: str(epNum)
      })
    })
      .then((res) => res.json())
      .then(() => {
        // Refresh local history
        return fetch('/api/history').then((res) => res.json());
      })
      .then((data) => setHistory(data || {}))
      .catch((err) => console.error("Error toggling watched:", err));
  };

  const str = (val) => String(val);

  const handleMarkSeasonWatched = () => {
    const title = details?.title || anime?.title;
    const sName = selectedSeason?.name || 'Saison 1';
    const epIds = episodes.map((ep) => str(ep.num || ep.title || '1'));

    fetch('/api/history/mark-season', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        anime_title: title,
        season: sName,
        ep_ids: epIds,
        watched: true
      })
    })
      .then(() => fetch('/api/history').then((res) => res.json()))
      .then((data) => setHistory(data || {}))
      .catch((err) => console.error("Error marking season:", err));
  };

  if (!anime) return null;

  const currentSeasonName = selectedSeason?.name || 'Saison 1';

  return (
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
          maxWidth: '850px',
          maxHeight: '88vh',
          borderRadius: 'var(--radius-md)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          position: 'relative'
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
            <Loader2 className="animate-spin" size={24} color="var(--primary)" />
            <span>Chargement...</span>
          </div>
        ) : (
          <div style={{ overflowY: 'auto', padding: '24px' }}>
            {/* Header Info */}
            <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
              <img
                src={details?.cover || anime.cover || 'https://via.placeholder.com/180x260'}
                alt={details?.title || anime.title}
                style={{
                  width: '160px',
                  height: '230px',
                  objectFit: 'cover',
                  borderRadius: 'var(--radius-sm)'
                }}
              />
              <div style={{ flex: 1, minWidth: '260px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <span className={`badge ${anime.source === 'anime_sama' ? 'badge-anime-sama' : 'badge-voiranime'}`} style={{ width: 'fit-content' }}>
                  {anime.source === 'anime_sama' ? 'Anime-Sama' : 'VoirAnime'}
                </span>
                <h2 style={{ fontSize: '1.6rem', fontWeight: 800 }}>{details?.title || anime.title}</h2>
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

            {/* Episode List Section */}
            <div style={{ marginTop: '28px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>
                  Épisodes ({episodes.length})
                </h3>
                {episodes.length > 0 && (
                  <div style={{ display: 'flex', gap: '8px' }}>
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
                      onClick={() => onDownloadBulk(details?.title || anime.title, currentSeasonName, episodes)}
                    >
                      <Download size={14} /> Tout Télécharger
                    </button>
                  </div>
                )}
              </div>

              {isLoadingEpisodes ? (
                <div style={{ padding: '40px', textAlign: 'center' }}>
                  <Loader2 className="animate-spin" size={24} color="var(--primary)" />
                </div>
              ) : episodes.length === 0 ? (
                <p style={{ color: 'var(--text-muted)' }}>Aucun épisode trouvé.</p>
              ) : (
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))',
                  gap: '10px',
                  maxHeight: '320px',
                  overflowY: 'auto'
                }}>
                  {episodes.map((ep, idx) => {
                    const epNum = ep.num || ep.title || idx + 1;
                    const watched = isEpisodeWatched(currentSeasonName, epNum);

                    return (
                      <div
                        key={idx}
                        className="surface-card"
                        style={{
                          padding: '10px',
                          borderRadius: 'var(--radius-sm)',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '8px',
                          border: watched ? '1px solid rgba(46, 160, 67, 0.4)' : '1px solid var(--border-color)'
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: watched ? '#3FB950' : '#fff' }}>
                            {ep.title || `Épisode ${epNum}`}
                          </span>
                          {watched && (
                            <span className="badge badge-watched">✓ Vu</span>
                          )}
                        </div>

                        <div style={{ display: 'flex', gap: '4px' }}>
                          <button
                            className="btn btn-primary"
                            style={{ flex: 1, padding: '4px 8px', fontSize: '0.78rem' }}
                            onClick={() => onPlayEpisode(details?.title || anime.title, currentSeasonName, ep, episodes)}
                          >
                            <Play size={12} fill="#fff" /> Lire
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
                            className="btn btn-secondary btn-icon"
                            style={{ width: '28px', height: '28px' }}
                            onClick={() => onDownloadEpisode(details?.title || anime.title, currentSeasonName, ep)}
                            title="Télécharger"
                          >
                            <Download size={12} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
