import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Info } from 'lucide-react';
import WideThumb from './WideThumb';
import WatchlistButton from './WatchlistButton';

const VIDEO_DELAY = 700;      // ms of preview before the trailer starts
const RETRY_EMPTY = 60000;    // an empty preview is asked again later: AniList may have answered meanwhile
const SOURCE_LABELS = { anime_sama: 'Anime-Sama', voiranime: 'VoirAnime' };
const cache = new Map();      // entity id -> { at, full, promise }

// Lazy: only a card hovered long enough asks the server, which answers from its caches only
const loadPreview = (anime) => {
  const id = anime.id || '';
  if (!id.startsWith('a-')) return Promise.resolve(null);
  const hit = cache.get(id);
  if (hit && (hit.full || Date.now() - hit.at < RETRY_EMPTY)) return hit.promise;
  const entry = { at: Date.now(), full: false, promise: null };
  entry.promise = fetch(`/api/anime/${encodeURIComponent(id)}/preview?${new URLSearchParams({ title: anime.title || '' })}`)
    .then((res) => (res.ok ? res.json() : null))
    .catch(() => null)
    .then((preview) => {
      entry.full = Boolean(preview && (preview.synopsis || preview.trailer));
      return preview;
    });
  cache.set(id, entry);
  return entry.promise;
};

// No autoplaying video for people who asked for less motion or less data
const quietMode = () =>
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || Boolean(navigator.connection?.saveData);

export default function AnimePreview({ anime, anchor, watchlisted, onToggleWatchlist, onSelect, onEnter, onLeave, onDismiss }) {
  const [preview, setPreview] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [playVideo, setPlayVideo] = useState(false);
  const [videoReady, setVideoReady] = useState(false);
  const [height, setHeight] = useState(0);
  const panelRef = useRef(null);
  const dismissRef = useRef(onDismiss);
  dismissRef.current = onDismiss;

  useEffect(() => {
    let alive = true;
    loadPreview(anime).then((p) => {
      if (!alive) return;
      setPreview(p);
      setIsLoading(false);
    });
    return () => { alive = false; };
  }, [anime.id]);

  const trailerId = preview?.trailer?.site === 'youtube' ? preview.trailer.id : null;
  useEffect(() => {
    if (!trailerId || quietMode()) return undefined;
    const timer = setTimeout(() => setPlayVideo(true), VIDEO_DELAY);
    return () => clearTimeout(timer);
  }, [trailerId]);

  // Anchored to where the card was: any scroll or resize closes it rather than leaving it floating
  useEffect(() => {
    const dismiss = () => dismissRef.current();
    const onKey = (e) => { if (e.key === 'Escape') dismiss(); };
    window.addEventListener('scroll', dismiss, true);
    window.addEventListener('resize', dismiss);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('scroll', dismiss, true);
      window.removeEventListener('resize', dismiss);
      window.removeEventListener('keydown', onKey);
    };
  }, []);

  // Grows out of the card like YouTube's, kept inside the viewport (its real height is known after the first paint)
  useLayoutEffect(() => {
    const h = panelRef.current?.offsetHeight;
    if (h && h !== height) setHeight(h);
  });
  const viewportW = document.documentElement.clientWidth;
  const viewportH = window.innerHeight;
  const width = Math.min(380, Math.max(300, anchor.width * 1.7), viewportW - 16);
  const panelH = height || (width * 9) / 16 + 230;
  const left = Math.min(Math.max(8, anchor.left + anchor.width / 2 - width / 2), viewportW - width - 8);
  const top = Math.max(8, Math.min(anchor.top - 8, viewportH - panelH - 8));
  const origin = `${anchor.left + anchor.width / 2 - left}px ${anchor.top + anchor.height / 3 - top}px`;

  const sources = (anime.sources?.length ? anime.sources : [{ source: anime.source }])
    .map((s) => SOURCE_LABELS[s.source] || s.source).filter(Boolean);
  const facts = [
    preview?.year,
    preview?.seasons ? `${preview.seasons} saison${preview.seasons > 1 ? 's' : ''}` : null,
    preview?.versions?.length ? preview.versions.map((v) => v.toUpperCase()).join(' / ') : null,
    preview?.has_scans ? 'Scans' : null
  ].filter(Boolean);

  return createPortal(
    <div
      ref={panelRef}
      className="anime-preview"
      role="group"
      aria-label={`Aperçu : ${anime.title}`}
      onPointerEnter={onEnter}
      onPointerLeave={onLeave}
      onClick={onSelect}
      style={{ position: 'fixed', left, top, width, zIndex: 45, transformOrigin: origin }}
    >
      <div className="anime-preview-media">
        <WideThumb sources={preview?.banner ? [preview.banner] : []} cover={anime.cover} alt="" blur />
        {playVideo && (
          // Muted and click-through: the preview, not YouTube, takes the clicks
          <iframe
            title={`Bande-annonce : ${anime.title}`}
            src={`https://www.youtube-nocookie.com/embed/${trailerId}?autoplay=1&mute=1&controls=0&playsinline=1&rel=0&modestbranding=1&iv_load_policy=3&disablekb=1&loop=1&playlist=${trailerId}`}
            allow="autoplay; encrypted-media; picture-in-picture"
            tabIndex={-1}
            onLoad={() => setVideoReady(true)}
            style={{ opacity: videoReady ? 1 : 0 }}
          />
        )}
      </div>

      <div className="anime-preview-body">
        <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff', lineHeight: 1.3, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {anime.title}
        </h3>
        <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          {[...facts, ...sources].join(' · ')}
        </p>

        {preview?.genres?.length > 0 && (
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            {preview.genres.map((g) => (
              <span key={g} style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-main)', background: 'rgba(255,255,255,0.1)', padding: '2px 8px', borderRadius: '6px' }}>{g}</span>
            ))}
          </div>
        )}

        {isLoading ? (
          <div aria-hidden="true" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div className="skeleton-line" style={{ width: '100%' }} />
            <div className="skeleton-line" style={{ width: '70%' }} />
          </div>
        ) : preview?.synopsis?.text ? (
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.45, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
            {preview.synopsis.lang === 'en' && (
              <span className="badge" style={{ marginRight: '6px', fontSize: '0.62rem', padding: '1px 5px', background: 'rgba(255,255,255,0.1)' }}>EN</span>
            )}
            {preview.synopsis.text}
          </p>
        ) : null}

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '2px' }}>
          <button
            type="button"
            className="btn btn-primary"
            style={{ fontSize: '0.82rem', padding: '7px 14px', minHeight: '36px', borderRadius: 'var(--radius-full)' }}
            onClick={(e) => { e.stopPropagation(); onSelect(); }}
          >
            <Info size={15} /> Voir la fiche
          </button>
          {onToggleWatchlist && (
            <WatchlistButton
              variant="pill"
              active={watchlisted}
              onToggle={() => onToggleWatchlist(anime)}
              style={{ borderRadius: 'var(--radius-full)' }}
            />
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
