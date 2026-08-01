import React, { useState, useEffect } from 'react';
import { X, Play, Download, Layers, Check, Loader2 } from 'lucide-react';

export default function AnimeDetailModal({ anime, onClose, onPlayEpisode, onDownloadEpisode, onDownloadBulk }) {
  const [details, setDetails] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedSeason, setSelectedSeason] = useState(null);
  const [episodes, setEpisodes] = useState([]);
  const [isLoadingEpisodes, setIsLoadingEpisodes] = useState(false);

  useEffect(() => {
    if (!anime) return;
    setIsLoading(true);

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

  if (!anime) return null;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 50,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px',
      background: 'rgba(0, 0, 0, 0.8)',
      backdropFilter: 'blur(12px)'
    }} onClick={onClose}>
      <div
        className="glass-modal animate-fade-in"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '900px',
          maxHeight: '90vh',
          borderRadius: 'var(--radius-lg)',
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
            top: '16px',
            right: '16px',
            zIndex: 10,
            background: 'rgba(0,0,0,0.5)',
            border: 'none'
          }}
        >
          <X size={20} />
        </button>

        {isLoading ? (
          <div style={{ padding: '80px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px' }}>
            <Loader2 className="animate-spin" size={28} color="var(--primary)" />
            <span>Chargement des détails de l'anime...</span>
          </div>
        ) : (
          <div style={{ overflowY: 'auto', padding: '30px' }}>
            {/* Header / Info Section */}
            <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
              <img
                src={details?.cover || anime.cover || 'https://via.placeholder.com/200x280'}
                alt={details?.title || anime.title}
                style={{
                  width: '180px',
                  height: '250px',
                  objectFit: 'cover',
                  borderRadius: 'var(--radius-md)',
                  boxShadow: '0 8px 25px rgba(0,0,0,0.5)'
                }}
              />
              <div style={{ flex: 1, minWidth: '280px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <span className={`badge ${anime.source === 'anime_sama' ? 'badge-anime-sama' : 'badge-voiranime'}`} style={{ width: 'fit-content' }}>
                  {anime.source === 'anime_sama' ? 'Anime-Sama' : 'VoirAnime'}
                </span>
                <h2 style={{ fontSize: '1.8rem', fontWeight: 800 }}>{details?.title || anime.title}</h2>
                {details?.synopsis && (
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.92rem', lineHeight: '1.6', maxHeight: '100px', overflowY: 'auto' }}>
                    {details.synopsis}
                  </p>
                )}

                {/* Season Pills */}
                {details?.seasons && details.seasons.length > 0 && (
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '10px' }}>
                    {details.seasons.map((s, idx) => (
                      <button
                        key={idx}
                        className={`btn ${selectedSeason?.name === s.name ? 'btn-primary' : 'btn-secondary'}`}
                        style={{ padding: '6px 14px', fontSize: '0.85rem' }}
                        onClick={() => handleSeasonChange(s)}
                      >
                        {s.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Episodes List Section */}
            <div style={{ marginTop: '32px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 700 }}>
                  Épisodes ({episodes.length})
                </h3>
                {episodes.length > 0 && (
                  <button
                    className="btn btn-secondary"
                    style={{ fontSize: '0.85rem' }}
                    onClick={() => onDownloadBulk(anime.title, selectedSeason?.name || 'Saison 1', episodes)}
                  >
                    <Download size={16} /> Tout Télécharger
                  </button>
                )}
              </div>

              {isLoadingEpisodes ? (
                <div style={{ padding: '40px', textAlign: 'center' }}>
                  <Loader2 className="animate-spin" size={24} color="var(--primary)" />
                </div>
              ) : episodes.length === 0 ? (
                <p style={{ color: 'var(--text-muted)' }}>Aucun épisode trouvé pour cette saison.</p>
              ) : (
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
                  gap: '12px',
                  maxHeight: '300px',
                  overflowY: 'auto',
                  paddingRight: '6px'
                }}>
                  {episodes.map((ep, idx) => (
                    <div
                      key={idx}
                      className="glass"
                      style={{
                        padding: '12px',
                        borderRadius: 'var(--radius-sm)',
                        display: 'flex',
                        flexDirection: 'column',
                        justify: 'space-between',
                        gap: '10px',
                        transition: 'var(--transition)'
                      }}
                    >
                      <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>{ep.title || `Épisode ${ep.num || idx + 1}`}</span>
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button
                          className="btn btn-primary"
                          style={{ flex: 1, padding: '6px', fontSize: '0.8rem' }}
                          onClick={() => onPlayEpisode(anime, selectedSeason?.name || 'Saison 1', ep, episodes)}
                        >
                          <Play size={14} fill="#000" /> Lire
                        </button>
                        <button
                          className="btn btn-secondary btn-icon"
                          style={{ width: '32px', height: '32px' }}
                          onClick={() => onDownloadEpisode(anime.title, selectedSeason?.name || 'Saison 1', ep)}
                          title="Télécharger"
                        >
                          <Download size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
