import React from 'react';
import { Play, Tv, Film, Info } from 'lucide-react';

export default function CatalogGrid({ results, isLoading, onSelectAnime }) {
  if (isLoading) {
    return (
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: '24px',
        padding: '30px 0'
      }}>
        {[...Array(10)].map((_, i) => (
          <div key={i} className="glass" style={{ borderRadius: 'var(--radius-md)', height: '300px', opacity: 0.5, animation: 'pulseGlow 1.5s infinite' }}></div>
        ))}
      </div>
    );
  }

  if (!results || results.length === 0) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '400px',
        textAlign: 'center',
        gap: '16px',
        color: 'var(--text-muted)'
      }}>
        <div style={{
          width: '80px',
          height: '80px',
          borderRadius: '50%',
          background: 'rgba(255, 255, 255, 0.05)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '2.5rem'
        }}>
          🔍
        </div>
        <h3 style={{ fontSize: '1.4rem', color: '#fff' }}>Aucun anime trouvé</h3>
        <p style={{ maxWidth: '400px', fontSize: '0.9rem' }}>
          Taper un mot-clé dans la barre de recherche ci-dessus pour parcourir Anime-Sama et VoirAnime.
        </p>
      </div>
    );
  }

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))',
      gap: '24px',
      padding: '30px 0'
    }}>
      {results.map((anime, index) => {
        const isAnimeSama = anime.source === 'anime_sama';
        return (
          <div
            key={anime.id || index}
            className="glass animate-fade-in"
            onClick={() => onSelectAnime(anime)}
            style={{
              borderRadius: 'var(--radius-md)',
              overflow: 'hidden',
              cursor: 'pointer',
              position: 'relative',
              transition: 'var(--transition)',
              display: 'flex',
              flexDirection: 'column',
              border: '1px solid var(--border-color)'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-6px)';
              e.currentTarget.style.borderColor = 'var(--primary-glow)';
              e.currentTarget.style.boxShadow = '0 10px 30px rgba(0, 240, 255, 0.15)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.borderColor = 'var(--border-color)';
              e.currentTarget.style.boxShadow = 'none';
            }}
          >
            {/* Poster Image */}
            <div style={{ position: 'relative', width: '100%', height: '280px', overflow: 'hidden', background: '#121724' }}>
              <img
                src={anime.cover || 'https://via.placeholder.com/280x380/0d1322/00f0ff?text=NAMI'}
                alt={anime.title}
                onError={(e) => {
                  e.target.src = 'https://via.placeholder.com/280x380/0d1322/00f0ff?text=NAMI';
                }}
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover',
                  transition: 'transform 0.4s ease'
                }}
              />

              {/* Source Badge */}
              <div style={{ position: 'absolute', top: '12px', left: '12px', zIndex: 10 }}>
                <span className={`badge ${isAnimeSama ? 'badge-anime-sama' : 'badge-voiranime'}`}>
                  {isAnimeSama ? 'Anime-Sama' : 'VoirAnime'}
                </span>
              </div>

              {/* Hover Overlay Button */}
              <div style={{
                position: 'absolute',
                inset: 0,
                background: 'linear-gradient(to top, rgba(8, 12, 20, 0.95), transparent)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                opacity: 0,
                transition: 'opacity 0.3s ease'
              }}
              className="card-overlay"
              onMouseEnter={(e) => e.currentTarget.style.opacity = '1'}
              onMouseLeave={(e) => e.currentTarget.style.opacity = '0'}
              >
                <div style={{
                  width: '54px',
                  height: '54px',
                  borderRadius: '50%',
                  background: 'var(--primary)',
                  color: '#000',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 0 20px var(--primary)'
                }}>
                  <Play size={24} fill="#000" style={{ marginLeft: '4px' }} />
                </div>
              </div>
            </div>

            {/* Title & Info */}
            <div style={{ padding: '14px', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <h3 style={{
                fontSize: '1rem',
                fontWeight: 700,
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
  );
}
