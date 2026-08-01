import React from 'react';
import { Play } from 'lucide-react';

export default function CatalogGrid({ results, isLoading, onSelectAnime }) {
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
            opacity: 0.4
          }}></div>
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
        minHeight: '350px',
        textAlign: 'center',
        gap: '12px',
        color: 'var(--text-muted)'
      }}>
        <div style={{
          width: '60px',
          height: '60px',
          borderRadius: '50%',
          background: '#21262D',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '1.8rem'
        }}>
          🔍
        </div>
        <h3 style={{ fontSize: '1.2rem', color: '#fff' }}>Aucun résultat</h3>
        <p style={{ maxWidth: '380px', fontSize: '0.88rem' }}>
          Rechercher un anime ci-dessus ou cliquer sur "Actualiser DB" pour peupler le catalogue.
        </p>
      </div>
    );
  }

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
      gap: '16px',
      padding: '24px 0'
    }}>
      {results.map((anime, index) => {
        const isAnimeSama = anime.source === 'anime_sama';
        return (
          <div
            key={anime.id || index}
            className="animate-fade-in"
            onClick={() => onSelectAnime(anime)}
            style={{
              borderRadius: 'var(--radius-sm)',
              overflow: 'hidden',
              cursor: 'pointer',
              position: 'relative',
              transition: 'var(--transition)',
              display: 'flex',
              flexDirection: 'column',
              background: 'var(--bg-card)',
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
            {/* Poster Image */}
            <div style={{ position: 'relative', width: '100%', height: '260px', overflow: 'hidden', background: '#0D1117' }}>
              <img
                src={anime.cover || 'https://via.placeholder.com/280x380/0d1117/8b949e?text=No+Image'}
                alt={anime.title}
                onError={(e) => {
                  e.target.src = 'https://via.placeholder.com/280x380/0d1117/8b949e?text=No+Image';
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

              {/* Source Badge */}
              <div style={{ position: 'absolute', top: '8px', left: '8px', zIndex: 5 }}>
                <span className={`badge ${isAnimeSama ? 'badge-anime-sama' : 'badge-voiranime'}`}>
                  {isAnimeSama ? 'Anime-Sama' : 'VoirAnime'}
                </span>
              </div>

              {/* Hover Overlay */}
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

            {/* Title */}
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
  );
}
