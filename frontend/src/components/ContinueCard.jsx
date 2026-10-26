import React from 'react';
import { Play, SkipForward, HardDrive, Info, Loader2 } from 'lucide-react';
import WideThumb from './WideThumb';
import { formatRemaining } from '../utils/animes';

export default function ContinueCard({ item, isResuming, onResume, onOpenAnime }) {
  const timeBadge = item.is_next
    ? 'Épisode suivant'
    : item.remaining_sec != null ? `Il reste ${formatRemaining(item.remaining_sec)}` : null;

  // The whole card is the tap target
  return (
    <div
      className="continue-card animate-fade-in"
      role="button"
      tabIndex={0}
      aria-label={`Reprendre ${item.display_title}, ${item.episode_title}, ${item.season}`}
      onClick={() => onResume(item)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onResume(item);
        }
      }}
      style={{ display: 'flex', flexDirection: 'column', gap: '8px', cursor: 'pointer', minWidth: 0, touchAction: 'manipulation' }}
    >
      <div
        className="continue-thumb"
        style={{
          position: 'relative',
          width: '100%',
          aspectRatio: '16 / 9',
          borderRadius: 'var(--radius-md)',
          overflow: 'hidden',
          background: '#0F0F0F',
          border: '1px solid var(--border-color)'
        }}
      >
        <WideThumb sources={item.wide_images || []} cover={item.cover} alt="" blur />

        {/* Play overlay: decorative, shown on mouse hover only (see index.css) */}
        <div
          className="continue-play"
          aria-hidden="true"
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(0,0,0,0.3)',
            pointerEvents: 'none'
          }}
        >
          <div style={{
            width: '44px',
            height: '44px',
            borderRadius: '50%',
            background: 'var(--yt-red)',
            color: '#fff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            {item.is_next ? <SkipForward size={20} /> : <Play size={20} fill="#fff" style={{ marginLeft: '2px' }} />}
          </div>
        </div>

        {(item.version === 'vf' || item.file_path) && (
          <div style={{ position: 'absolute', top: '8px', left: '8px', display: 'flex', gap: '4px' }}>
            {item.version === 'vf' && (
              <span className="badge" style={{ background: 'rgba(0,0,0,0.8)', color: '#fff', padding: '2px 6px', fontSize: '0.65rem' }}>
                VF
              </span>
            )}
            {item.file_path && (
              <span className="badge" style={{ background: 'rgba(46, 160, 67, 0.85)', color: '#fff', padding: '2px 6px', fontSize: '0.65rem' }}>
                <HardDrive size={10} /> Disque
              </span>
            )}
          </div>
        )}

        {timeBadge && (
          <div style={{
            position: 'absolute',
            right: '8px',
            bottom: '10px',
            background: 'rgba(0,0,0,0.85)',
            color: '#fff',
            padding: '2px 6px',
            borderRadius: '4px',
            fontSize: '0.72rem',
            fontWeight: 700
          }}>
            {timeBadge}
          </div>
        )}

        {!item.is_next && item.position_sec > 0 && (
          <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: '4px', background: 'rgba(255,255,255,0.25)' }}>
            <div style={{ width: `${Math.min(100, Math.max(2, item.progress_percent))}%`, height: '100%', background: 'var(--yt-red)' }}></div>
          </div>
        )}

        {isResuming && (
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Loader2 className="animate-spin" size={26} color="#fff" />
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', minWidth: 0 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{
            fontSize: '0.9rem',
            fontWeight: 700,
            color: '#fff',
            lineHeight: 1.3,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden'
          }}>
            {item.display_title}
          </h3>
          {/* Two lines, episode first: on a phone card it is what must stay visible */}
          <p style={{
            fontSize: '0.78rem',
            color: 'var(--text-muted)',
            marginTop: '2px',
            lineHeight: 1.3,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden'
          }}>
            {`${item.is_next ? 'À suivre · ' : ''}${item.episode_title} · ${item.season}`}
          </p>
        </div>

        {/* Away from the thumbnail, the main tap area */}
        {item.anime && (
          <button
            type="button"
            className="card-action card-action-flat"
            aria-label="Voir la fiche de l'anime"
            title="Voir la fiche de l'anime"
            onClick={(e) => {
              e.stopPropagation();
              onOpenAnime(item);
            }}
            onKeyDown={(e) => e.stopPropagation()}
          >
            <Info size={16} />
          </button>
        )}
      </div>
    </div>
  );
}
