import React from 'react';
import { Play, RotateCcw, Shuffle, Sparkles, History, Film, Bookmark } from 'lucide-react';

import ContinueCard from './ContinueCard';
import WatchlistButton from './WatchlistButton';
import { DEFAULT_ANIME_COVER, imageFallback } from '../utils/placeholders';

const SOURCE_LABELS = { anime_sama: 'Anime-Sama', voiranime: 'VoirAnime' };

// Merged entities list every source that has the anime
const hasSource = (anime, source) =>
  anime.source === source || (anime.sources || []).some((s) => s.source === source);

export { DEFAULT_ANIME_COVER };

export default function CatalogGrid({
  results = [],
  isLoading,
  searchQuery,
  activeSource = 'all',
  continueWatching = [],
  recentAnimes = [],
  randomSuggestions = [],
  watchlist = [],
  isInWatchlist = () => false,
  onToggleWatchlist,
  onOpenWatchlist,
  resumingKey,
  onRollRandom,
  onSelectAnime,
  onResumeEpisode
}) {
  const filteredContinueWatching = (continueWatching || []).filter((item) => {
    if (activeSource === 'all') return true;
    if (item.source) return item.source === activeSource;
    return true;
  });

  const filteredWatchlist = (watchlist || []).filter((anime) => activeSource === 'all' || hasSource(anime, activeSource));

  const filteredRecentAnimes = (recentAnimes || []).filter((anime) => {
    if (activeSource === 'all') return true;
    return hasSource(anime, activeSource);
  });

  const filteredRandomSuggestions = (randomSuggestions || []).filter((anime) => {
    if (activeSource === 'all') return true;
    return hasSource(anime, activeSource);
  });

  const filteredResults = (results || []).filter((anime) => {
    if (activeSource === 'all') return true;
    return hasSource(anime, activeSource);
  });

  const isBrowsingHome = !searchQuery.trim();

  return (
    <div style={{ padding: '24px 0', display: 'flex', flexDirection: 'column', gap: '32px' }}>
      {/* 1. Continuer la lecture (Resume Watching Shelf) */}
      {isBrowsingHome && filteredContinueWatching && filteredContinueWatching.length > 0 && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <RotateCcw size={18} color="var(--primary)" />
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#fff' }}>Continuer la lecture</h2>
          </div>

          {/* 2 columns on phones, 5 at 1440 px, without a media query */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(clamp(140px, 40vw, 250px), 1fr))',
            gap: '16px 12px'
          }}>
            {filteredContinueWatching.slice(0, 8).map((item) => (
              <ContinueCard
                key={item.key}
                item={item}
                isResuming={resumingKey === item.key}
                onResume={onResumeEpisode}
                onOpenAnime={(i) => onSelectAnime({ ...i.anime, cover: i.cover })}
              />
            ))}
          </div>
        </section>
      )}

      {/* À regarder plus tard (Watchlist Shelf) */}
      {isBrowsingHome && filteredWatchlist.length > 0 && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Bookmark size={18} color="var(--accent-yellow)" />
              <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#fff' }}>À regarder plus tard</h2>
            </div>
            <button
              className="btn btn-secondary"
              style={{ fontSize: '0.78rem', padding: '4px 10px', minHeight: '32px' }}
              onClick={onOpenWatchlist}
            >
              Tout voir ({filteredWatchlist.length})
            </button>
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(clamp(96px, 26vw, 160px), 1fr))',
            gap: '10px'
          }}>
            {filteredWatchlist.slice(0, 6).map((anime) => (
              <div
                key={anime.id || anime.url}
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
                <div style={{ position: 'relative', width: '100%', aspectRatio: '2 / 3', overflow: 'hidden', background: '#0D1117' }}>
                  <img
                    src={anime.cover || DEFAULT_ANIME_COVER}
                    loading="lazy"
                    decoding="async"
                    alt={anime.title}
                    onError={imageFallback(anime.cover_fallbacks || [], DEFAULT_ANIME_COVER)}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                  <WatchlistButton active onToggle={() => onToggleWatchlist(anime)} />
                </div>
                <div style={{ padding: '8px 10px' }}>
                  <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#fff', lineHeight: 1.3, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {anime.title}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 2. Récemment consultés & Recherchés */}
      {isBrowsingHome && filteredRecentAnimes && filteredRecentAnimes.length > 0 && (
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
            {filteredRecentAnimes.slice(0, 6).map((anime, idx) => (
              <div
                key={anime.id || idx}
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
                <div style={{ position: 'relative', width: '100%', height: '180px', overflow: 'hidden', background: '#0D1117' }}>
                  <img
                    src={anime.cover || DEFAULT_ANIME_COVER}
                    loading="lazy"
                    decoding="async"
                    alt={anime.title}
                    onError={imageFallback(anime.cover_fallbacks || [], DEFAULT_ANIME_COVER)}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                  <WatchlistButton active={isInWatchlist(anime)} onToggle={() => onToggleWatchlist(anime)} />
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
      {isBrowsingHome && filteredRandomSuggestions && filteredRandomSuggestions.length > 0 && (
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
            {filteredRandomSuggestions.slice(0, 6).map((anime, idx) => (
              <div
                key={anime.id || idx}
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
                <div style={{ position: 'relative', width: '100%', height: '220px', overflow: 'hidden', background: '#0D1117' }}>
                  <img
                    src={anime.cover || DEFAULT_ANIME_COVER}
                    loading="lazy"
                    decoding="async"
                    alt={anime.title}
                    onError={imageFallback(anime.cover_fallbacks || [], DEFAULT_ANIME_COVER)}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                  <WatchlistButton active={isInWatchlist(anime)} onToggle={() => onToggleWatchlist(anime)} />
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
            {/* No count while loading: it would still be the previous search's */}
            {searchQuery ? `Résultats pour "${searchQuery}"${isLoading ? '' : ` (${filteredResults.length})`}` : 'Catalogue complet'}
          </h2>
        </div>

        {/* Skeleton here only: the shelves above stay visible while the catalogue reloads */}
        {isLoading ? (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
            gap: '16px'
          }}>
            {[...Array(12)].map((_, i) => (
              <div key={i} className="surface-card" style={{
                borderRadius: 'var(--radius-sm)',
                height: '280px',
                opacity: 0.3
              }}></div>
            ))}
          </div>
        ) : filteredResults.length === 0 ? (
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
            {filteredResults.map((anime, index) => {
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
                      src={anime.cover || DEFAULT_ANIME_COVER}
                    loading="lazy"
                    decoding="async"
                      alt={anime.title}
                      onError={imageFallback(anime.cover_fallbacks || [], DEFAULT_ANIME_COVER)}
                      style={{
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover',
                        transition: 'transform 0.3s ease'
                      }}
                      onMouseEnter={(e) => e.target.style.transform = 'scale(1.05)'}
                      onMouseLeave={(e) => e.target.style.transform = 'scale(1)'}
                    />

                    <div style={{ position: 'absolute', top: '8px', left: '8px', zIndex: 5, display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                      {(anime.sources?.length ? anime.sources : [{ source: anime.source }]).map((s) => (
                        <span key={s.source} className={`badge ${s.source === 'anime_sama' ? 'badge-anime-sama' : 'badge-voiranime'}`}>
                          {SOURCE_LABELS[s.source] || s.source}
                        </span>
                      ))}
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

                    <WatchlistButton active={isInWatchlist(anime)} onToggle={() => onToggleWatchlist(anime)} />
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
