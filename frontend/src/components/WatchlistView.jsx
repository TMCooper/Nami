import React, { useState, useEffect, useMemo } from 'react';
import { Bookmark, Play, Loader2 } from 'lucide-react';
import WatchlistButton from './WatchlistButton';
import { DEFAULT_ANIME_COVER, imageFallback } from '../utils/placeholders';
import { sameAnime, formatRelativeDate } from '../utils/animes';

const SOURCE_LABELS = { anime_sama: 'Anime-Sama', voiranime: 'VoirAnime' };

export default function WatchlistView({
  currentUser,
  watchlist = [],
  continueWatching = [],
  isInWatchlist,
  resumingKey = null,
  onReload,
  onSelectAnime,
  onToggleWatchlist,
  onResumeEpisode
}) {
  const [sortMode, setSortMode] = useState('recent'); // 'recent' | 'title'
  // Items removed during this visit stay (dimmed) so a mis-tap is undone by tapping again
  const [ghosts, setGhosts] = useState([]);

  // App owns the list: refresh it each time the tab opens
  useEffect(() => {
    onReload?.();
  }, []);

  const toggle = (item) => {
    const saved = isInWatchlist(item);
    if (saved) setGhosts((g) => [...g.filter((x) => !sameAnime(x, item)), item]);
    onToggleWatchlist(item, { restore: !saved }); // re-adding a ghost undoes its removal: it keeps its place
  };

  const rows = useMemo(() => {
    const list = [
      ...watchlist.map((item) => ({ item, ghost: false })),
      ...ghosts.filter((g) => !watchlist.some((w) => sameAnime(w, g))).map((item) => ({ item, ghost: true }))
    ];
    if (sortMode === 'title') {
      list.sort((a, b) => (a.item.title || '').localeCompare(b.item.title || '', 'fr'));
    } else {
      list.sort((a, b) => (b.item.added_at || 0) - (a.item.added_at || 0));
    }
    return list;
  }, [watchlist, ghosts, sortMode]);

  return (
    <div style={{ padding: '24px 0', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header Toolbar */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '16px',
        paddingBottom: '16px',
        borderBottom: '1px solid var(--border-color)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: '42px',
            height: '42px',
            borderRadius: '10px',
            background: 'linear-gradient(135deg, rgba(210, 153, 34, 0.15), rgba(88, 166, 255, 0.15))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '1px solid rgba(255, 255, 255, 0.1)'
          }}>
            <Bookmark size={22} color="var(--accent-yellow)" />
          </div>
          <div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 800, color: '#fff', letterSpacing: '-0.02em', margin: 0 }}>
              À regarder plus tard
            </h2>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '2px 0 0 0' }}>
              {rows.length} anime(s) • Profil de {currentUser?.username || 'Utilisateur'}
            </p>
          </div>
        </div>

        {/* Sort */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <button
            className={`btn ${sortMode === 'recent' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setSortMode('recent')}
            style={{ fontSize: '0.78rem', padding: '5px 12px', borderRadius: 'var(--radius-full)' }}
          >
            Récemment ajoutés
          </button>
          <button
            className={`btn ${sortMode === 'title' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setSortMode('title')}
            style={{ fontSize: '0.78rem', padding: '5px 12px', borderRadius: 'var(--radius-full)' }}
          >
            Titre (A-Z)
          </button>
        </div>
      </div>

      {/* Empty State */}
      {rows.length === 0 ? (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '320px',
          gap: '12px',
          color: 'var(--text-muted)'
        }}>
          <Bookmark size={44} style={{ opacity: 0.25 }} />
          <h3 style={{ fontSize: '1.15rem', color: '#fff' }}>Votre liste est vide</h3>
          <p style={{ fontSize: '0.85rem', maxWidth: '400px', textAlign: 'center' }}>
            Ajoutez un anime avec le signet de sa carte ou de sa fiche pour le retrouver ici.
          </p>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(clamp(130px, 40vw, 170px), 1fr))',
          gap: '14px'
        }}>
          {rows.map(({ item, ghost }) => {
            const resume = continueWatching.find((c) => c.anime && sameAnime(c.anime, item));
            const isResuming = Boolean(resume) && resumingKey === resume.key; // waiting for its season list
            return (
              <div
                key={item.id || item.url}
                className="surface-card animate-fade-in"
                onClick={() => onSelectAnime(item)}
                style={{
                  borderRadius: 'var(--radius-sm)',
                  overflow: 'hidden',
                  cursor: 'pointer',
                  border: '1px solid var(--border-color)',
                  display: 'flex',
                  flexDirection: 'column',
                  opacity: ghost ? 0.45 : 1,
                  transition: 'var(--transition)'
                }}
              >
                <div style={{ position: 'relative', width: '100%', aspectRatio: '2 / 3', background: '#0D1117', overflow: 'hidden' }}>
                  <img
                    src={item.cover || DEFAULT_ANIME_COVER}
                    loading="lazy"
                    decoding="async"
                    alt={item.title}
                    onError={imageFallback(item.cover_fallbacks || [], DEFAULT_ANIME_COVER)}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />

                  <div style={{ position: 'absolute', top: '8px', left: '8px', zIndex: 5, display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                    {(item.sources?.length ? item.sources : [{ source: item.source }]).map((s) => (
                      <span key={s.source} className={`badge ${s.source === 'anime_sama' ? 'badge-anime-sama' : 'badge-voiranime'}`}>
                        {SOURCE_LABELS[s.source] || s.source}
                      </span>
                    ))}
                  </div>

                  <WatchlistButton active={!ghost} onToggle={() => toggle(item)} />

                  {resume && !resume.is_next && (
                    <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: '4px', background: 'rgba(255,255,255,0.25)' }}>
                      <div style={{ width: `${Math.min(100, Math.max(2, resume.progress_percent))}%`, height: '100%', background: 'var(--yt-red)' }}></div>
                    </div>
                  )}
                </div>

                <div style={{ padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff', lineHeight: 1.3, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {item.title}
                  </span>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                    Ajouté {formatRelativeDate(item.added_at).toLowerCase()}
                  </span>
                  {resume && (
                    <button
                      className="btn btn-primary"
                      style={{ width: '100%', minHeight: '36px', fontSize: '0.78rem', padding: '6px 10px', marginTop: 'auto' }}
                      aria-disabled={isResuming}
                      aria-busy={isResuming}
                      onClick={(e) => {
                        // Not `disabled`: the tap must still stop here, never open the card behind it
                        e.stopPropagation();
                        if (!isResuming) onResumeEpisode(resume);
                      }}
                    >
                      {isResuming ? <Loader2 className="animate-spin" size={12} /> : <Play size={12} fill="#fff" />}{' '}
                      {resume.is_next ? `Suivant · Ép. ${resume.episode_num}` : `Reprendre · Ép. ${resume.episode_num}`}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
