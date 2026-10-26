import React, { useState, useEffect, useMemo } from 'react';
import { Bookmark, Play, Loader2 } from 'lucide-react';
import AnimeCard from './AnimeCard';
import { sameAnime, formatRelativeDate } from '../utils/animes';

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
          <button className={`chip${sortMode === 'recent' ? ' active' : ''}`} onClick={() => setSortMode('recent')}>
            Récemment ajoutés
          </button>
          <button className={`chip${sortMode === 'title' ? ' active' : ''}`} onClick={() => setSortMode('title')}>
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
        <div className="card-grid">
          {rows.map(({ item, ghost }) => {
            const resume = continueWatching.find((c) => c.anime && sameAnime(c.anime, item));
            const isResuming = Boolean(resume) && resumingKey === resume.key; // waiting for its season list
            return (
              <AnimeCard
                key={item.id || item.url}
                anime={item}
                onSelect={onSelectAnime}
                watchlisted={!ghost}
                onToggleWatchlist={toggle}
                meta={`Ajouté ${formatRelativeDate(item.added_at).toLowerCase()}`}
                progress={resume && !resume.is_next ? resume.progress_percent : null}
                dimmed={ghost}
              >
                {resume && (
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', minHeight: '36px', fontSize: '0.78rem', padding: '6px 10px', marginTop: '6px', borderRadius: 'var(--radius-full)' }}
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
              </AnimeCard>
            );
          })}
        </div>
      )}
    </div>
  );
}
