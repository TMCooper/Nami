import React from 'react';
import { Play, RotateCcw, Shuffle, Sparkles, Clock, History, Film } from 'lucide-react';

export default function CatalogGrid({
  results,
  isLoading,
  searchQuery,
  continueWatching = [],
  recentAnimes = [],
  randomSuggestions = [],
  onRollRandom,
  onSelectAnime,
  onResumeEpisode
}) {
  const formatTime = (seconds) => {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  if (isLoading) {
    return (
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
        gap: '16px',
        padding: '24px 0'
      }}>
        {[...Array(12)].map((_, i) => (
          <div key={i} className="surface-card" style={{
            borderRadius: 'var(--radius-sm)',
            height: '280px',
            opacity: 0.3
          }}></div>
        ))}
      </div>
    );
  }

  const isBrowsingHome = !searchQuery.trim();

  return (
    <div style={{ padding: '24px 0', display: 'flex', flexDirection: 'column', gap: '32px' }}>
      {/* 1. Continuer la lecture (Resume Watching Shelf) */}
      {isBrowsingHome && continueWatching && continueWatching.length > 0 && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <RotateCcw size={18} color="var(--primary)" />
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#fff' }}>Continuer la lecture</h2>
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: '14px'
          }}>
            {continueWatching.slice(0, 6).map((item, idx) => (
              <div
                key={idx}
                className="surface-card animate-fade-in"
                style={{
                  padding: '14px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-color)',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '10px',
                  background: 'linear-gradient(145deg, rgba(22, 27, 34, 0.9), rgba(13, 17, 23, 0.9))'
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#fff', lineHeight: 1.3 }}>
                      {item.anime_title}
                    </h3>
                  </div>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '3px' }}>
                    {item.season} — Épisode {item.episode_num}
                  </p>
                </div>

                {/* Progress bar */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-dim)', marginBottom: '4px' }}>
                    <span>Progression</span>
                    <span>{formatTime(item.position_sec)} / {formatTime(item.duration_sec)}</span>
                  </div>
                  <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.08)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
                    <div style={{ width: `${Math.min(100, Math.max(5, item.progress_percent))}%`, height: '100%', background: 'linear-gradient(90deg, var(--primary), var(--accent-cyan))' }}></div>
                  </div>
                </div>

                {/* Resume button */}
                <button
                  className="btn btn-primary"
                  style={{ width: '100%', padding: '7px 12px', fontSize: '0.8rem' }}
                  onClick={() => onResumeEpisode(item)}
                >
                  <Play size={13} fill="#fff" /> Reprendre l'Épisode {item.episode_num}
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 2. Récemment consultés & Recherchés */}
      {isBrowsingHome && recentAnimes && recentAnimes.length > 0 && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <History size={18} color="var(--accent-cyan)" />
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#fff' }}>Récemment consultés & recherchés</h2>
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
            gap: '12px'
          }}>
            {recentAnimes.slice(0, 6).map((anime, idx) => (
              <div
                key={idx}
                className="surface-card animate-fade-in"
                onClick={() => onSelectAnime(anime)}
                style={{
                  borderRadius: 'var(--radius-sm)',
                  overflow: 'hidden',
                  cursor: 'pointer',
                  border: '1px solid var(--border-color)',
                  transition: 'var(--transition)'
                }}
                onMouseEnter={(e) => e.currentTarget.style.transform = 'translateY(-3px)'}
                onMouseLeave={(e) => e.currentTarget.style.transform = 'translateY(0)'}
              >
                <div style={{ width: '100%', height: '180px', overflow: 'hidden', background: '#0D1117' }}>
                  <img
                    src={anime.cover || 'https://via.placeholder.com/200x280/0d1117/8b949e?text=Anime'}
                    alt={anime.title}
                    onError={(e) => { e.target.src = 'https://via.placeholder.com/200x280/0d1117/8b949e?text=Anime'; }}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                </div>
                <div style={{ padding: '8px 10px' }}>
                  <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#fff', display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {anime.title}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 3. Découverte & Aléatoire */}
      {isBrowsingHome && randomSuggestions && randomSuggestions.length > 0 && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Sparkles size={18} color="#E3B341" />
              <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#fff' }}>Découvertes & Aléatoire</h2>
            </div>
            {onRollRandom && (
              <button
                className="btn btn-secondary"
                style={{ fontSize: '0.78rem', padding: '4px 10px', gap: '5px' }}
                onClick={onRollRandom}
              >
                <Shuffle size={13} /> Tirer au sort
              </button>
            )}
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))',
            gap: '14px'
          }}>
            {randomSuggestions.slice(0, 6).map((anime, idx) => (
              <div
                key={idx}
                className="surface-card animate-fade-in"
                onClick={() => onSelectAnime(anime)}
                style={{
                  borderRadius: 'var(--radius-sm)',
                  overflow: 'hidden',
                  cursor: 'pointer',
                  border: '1px solid var(--border-color)',
                  transition: 'var(--transition)'
                }}
                onMouseEnter={(e) => e.currentTarget.style.transform = 'translateY(-3px)'}
                onMouseLeave={(e) => e.currentTarget.style.transform = 'translateY(0)'}
              >
                <div style={{ width: '100%', height: '220px', overflow: 'hidden', background: '#0D1117' }}>
                  <img
                    src={anime.cover || 'https://via.placeholder.com/200x280/0d1117/8b949e?text=Anime'}
                    alt={anime.title}
                    onError={(e) => { e.target.src = 'https://via.placeholder.com/200x280/0d1117/8b949e?text=Anime'; }}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                </div>
                <div style={{ padding: '8px 10px' }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff', display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {anime.title}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 4. Catalogue / Résultats de recherche */}
      <section style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#fff' }}>
            {searchQuery ? `Résultats pour "${searchQuery}" (${results.length})` : 'Catalogue complet'}
          </h2>
        </div>

        {results.length === 0 ? (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '260px',
            textAlign: 'center',
            gap: '12px',
            color: 'var(--text-muted)'
          }}>
            <Film size={36} style={{ opacity: 0.3 }} />
            <h3 style={{ fontSize: '1.1rem', color: '#fff' }}>Aucun anime trouvé</h3>
            <p style={{ maxWidth: '380px', fontSize: '0.85rem' }}>
              Essayez un autre mot-clé ou cliquez sur "Actualiser DB" dans l'en-tête pour synchroniser les sources.
            </p>
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
            gap: '16px'
          }}>
            {results.map((anime, index) => {
              const isAnimeSama = anime.source === 'anime_sama';
              return (
                <div
                  key={anime.id || index}
                  className="surface-card animate-fade-in"
                  onClick={() => onSelectAnime(anime)}
                  style={{
                    borderRadius: 'var(--radius-sm)',
                    overflow: 'hidden',
                    cursor: 'pointer',
                    position: 'relative',
                    transition: 'var(--transition)',
                    display: 'flex',
                    flexDirection: 'column',
                    border: '1px solid var(--border-color)'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-4px)';
                    e.currentTarget.style.borderColor = 'var(--border-active)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'translateY(0)';
                    e.currentTarget.style.borderColor = 'var(--border-color)';
                  }}
                >
                  <div style={{ position: 'relative', width: '100%', height: '260px', overflow: 'hidden', background: '#0D1117' }}>
                    <img
                      src={anime.cover || 'https://via.placeholder.com/280x380/0d1117/8b949e?text=Anime'}
                      alt={anime.title}
                      onError={(e) => {
                        e.target.src = 'https://via.placeholder.com/280x380/0d1117/8b949e?text=Anime';
                      }}
                      style={{
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover',
                        transition: 'transform 0.3s ease'
                      }}
                      onMouseEnter={(e) => e.target.style.transform = 'scale(1.05)'}
                      onMouseLeave={(e) => e.target.style.transform = 'scale(1)'}
                    />

                    <div style={{ position: 'absolute', top: '8px', left: '8px', zIndex: 5 }}>
                      <span className={`badge ${isAnimeSama ? 'badge-anime-sama' : 'badge-voiranime'}`}>
                        {isAnimeSama ? 'Anime-Sama' : 'VoirAnime'}
                      </span>
                    </div>

                    <div
                      style={{
                        position: 'absolute',
                        inset: 0,
                        background: 'linear-gradient(to top, rgba(13, 17, 23, 0.9) 0%, transparent 50%)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        opacity: 0,
                        transition: 'opacity 0.25s ease'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.opacity = '1'}
                      onMouseLeave={(e) => e.currentTarget.style.opacity = '0'}
                    >
                      <div style={{
                        width: '44px',
                        height: '44px',
                        borderRadius: '50%',
                        background: 'var(--primary)',
                        color: '#fff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}>
                        <Play size={20} fill="#fff" style={{ marginLeft: '2px' }} />
                      </div>
                    </div>
                  </div>

                  <div style={{ padding: '10px 12px' }}>
                    <h3 style={{
                      fontSize: '0.9rem',
                      fontWeight: 600,
                      color: '#fff',
                      lineHeight: '1.3',
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden'
                    }}>
                      {anime.title}
                    </h3>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
