import React, { useEffect, useRef, useState } from 'react';
import AnimePreview from './AnimePreview';
import WatchlistButton from './WatchlistButton';
import { DEFAULT_ANIME_COVER, imageFallback } from '../utils/placeholders';

const SOURCE_LABELS = { anime_sama: 'Anime-Sama', voiranime: 'VoirAnime' };
const OPEN_DELAY = 550;   // ms of hover before the preview opens: passing over a card does nothing
const CLOSE_DELAY = 150;  // ms to move from the card into its preview

// One preview at a time across every grid
let closeOpenPreview = null;

// Only a real mouse previews: touch and pens never open one, so a tap always goes straight to the card
const canPreview = () => Boolean(window.matchMedia?.('(hover: hover) and (pointer: fine)').matches);

export const sourceLine = (anime) =>
  (anime.sources?.length ? anime.sources : [{ source: anime.source }])
    .map((s) => SOURCE_LABELS[s.source] || s.source)
    .filter(Boolean)
    .join(' · ');

export default function AnimeCard({
  anime,
  onSelect,
  watchlisted = false,
  onToggleWatchlist,
  meta,
  progress = null,
  dimmed = false,
  children
}) {
  const cardRef = useRef(null);
  const timersRef = useRef({ open: null, close: null });
  const [anchor, setAnchor] = useState(null); // card rectangle while its preview is open

  const clearTimers = () => {
    clearTimeout(timersRef.current.open);
    clearTimeout(timersRef.current.close);
  };
  // Stable across renders: the module-level "one preview at a time" compares it by identity
  const closePreview = useRef(() => {
    clearTimeout(timersRef.current.open);
    clearTimeout(timersRef.current.close);
    setAnchor(null);
  }).current;

  useEffect(() => () => {
    clearTimers();
    if (closeOpenPreview === closePreview) closeOpenPreview = null;
  }, []);

  const handleEnter = (e) => {
    clearTimeout(timersRef.current.close);
    if (e.pointerType !== 'mouse' || !canPreview() || anchor) return;
    clearTimeout(timersRef.current.open);
    timersRef.current.open = setTimeout(() => {
      if (!cardRef.current) return;
      if (closeOpenPreview && closeOpenPreview !== closePreview) closeOpenPreview();
      closeOpenPreview = closePreview;
      setAnchor(cardRef.current.getBoundingClientRect());
    }, OPEN_DELAY);
  };

  const handleLeave = () => {
    clearTimers();
    timersRef.current.close = setTimeout(() => setAnchor(null), CLOSE_DELAY);
  };

  const select = () => {
    closePreview();
    onSelect(anime);
  };

  return (
    <>
      <div
        ref={cardRef}
        className="anime-card animate-fade-in"
        role="button"
        tabIndex={0}
        aria-label={anime.title}
        onClick={select}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            select();
          }
        }}
        onPointerEnter={handleEnter}
        onPointerLeave={handleLeave}
        style={{ opacity: dimmed ? 0.45 : 1 }}
      >
        <div className="anime-card-thumb">
          <img
            src={anime.cover || DEFAULT_ANIME_COVER}
            loading="lazy"
            decoding="async"
            alt=""
            onError={imageFallback(anime.cover_fallbacks || [], DEFAULT_ANIME_COVER)}
          />
          {onToggleWatchlist && (
            <WatchlistButton active={watchlisted} onToggle={() => onToggleWatchlist(anime)} />
          )}
          {progress != null && (
            <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: '4px', background: 'rgba(255,255,255,0.25)' }}>
              <div style={{ width: `${Math.min(100, Math.max(2, progress))}%`, height: '100%', background: 'var(--yt-red)' }}></div>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0, flex: 1 }}>
          <h3 className="anime-card-title">{anime.title}</h3>
          <p className="anime-card-meta">{meta ?? sourceLine(anime)}</p>
          {children}
        </div>
      </div>

      {/* A sibling, not a child: events inside the portal must not bubble into the card */}
      {anchor && (
        <AnimePreview
          anime={anime}
          anchor={anchor}
          watchlisted={watchlisted}
          onToggleWatchlist={onToggleWatchlist}
          onSelect={select}
          onEnter={() => clearTimeout(timersRef.current.close)}
          onLeave={handleLeave}
          onDismiss={closePreview}
        />
      )}
    </>
  );
}

// Same footprint as a card, shown while a grid loads
export function AnimeCardSkeleton() {
  return (
    <div className="anime-card" aria-hidden="true" style={{ cursor: 'default' }}>
      <div className="anime-card-thumb skeleton-block" />
      <div className="skeleton-line" style={{ width: '85%' }} />
      <div className="skeleton-line" style={{ width: '50%' }} />
    </div>
  );
}
