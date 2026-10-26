import React, { useEffect, useState } from 'react';
import { RotateCcw, Shuffle, Sparkles, History, Film, Bookmark } from 'lucide-react';

import AnimeCard, { AnimeCardSkeleton } from './AnimeCard';
import ContinueCard from './ContinueCard';
import { DEFAULT_ANIME_COVER } from '../utils/placeholders';

export { DEFAULT_ANIME_COVER };

const PAGE_SIZE = 48; // catalogue cards rendered per step: the full catalogue is hundreds of cards

// Renders a long list a page at a time, the next page when the end comes near
// (back to the first page when the list itself changes)
function useProgressiveList(items) {
  const [count, setCount] = useState(PAGE_SIZE);
  // A callback ref: the sentinel only appears once the list has loaded, the observer must follow it
  const [sentinel, setSentinel] = useState(null);

  useEffect(() => { setCount(PAGE_SIZE); }, [items]);

  useEffect(() => {
    if (!sentinel || count >= items.length || !('IntersectionObserver' in window)) return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) setCount((c) => c + PAGE_SIZE);
    }, { rootMargin: '800px 0px' });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [sentinel, count, items.length]);

  return { visible: items.slice(0, count), hasMore: count < items.length, sentinelRef: setSentinel, showMore: () => setCount((c) => c + PAGE_SIZE) };
}

function Shelf({ icon, title, action, children }) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
        <h2 className="shelf-title">{icon}{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export default function CatalogGrid({
  results = [],
  isLoading,
  searchQuery,
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
  const filteredContinueWatching = continueWatching || [];
  const filteredWatchlist = watchlist || [];
  const filteredRecentAnimes = recentAnimes || [];
  const filteredRandomSuggestions = randomSuggestions || [];
  const filteredResults = results || [];
  const catalogue = useProgressiveList(filteredResults);

  const isBrowsingHome = !searchQuery.trim();

  const card = (anime, key) => (
    <AnimeCard
      key={key}
      anime={anime}
      onSelect={onSelectAnime}
      watchlisted={isInWatchlist(anime)}
      onToggleWatchlist={onToggleWatchlist}
    />
  );

  return (
    <div style={{ padding: '24px 0 40px', display: 'flex', flexDirection: 'column', gap: '36px' }}>
      {isBrowsingHome && filteredContinueWatching.length > 0 && (
        <Shelf icon={<RotateCcw size={18} color="var(--yt-red)" />} title="Continuer la lecture">
          {/* 2 columns on phones, 5 at 1440 px, without a media query */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(clamp(140px, 40vw, 250px), 1fr))',
            gap: '20px 12px'
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
        </Shelf>
      )}

      {isBrowsingHome && filteredWatchlist.length > 0 && (
        <Shelf
          icon={<Bookmark size={18} color="var(--accent-yellow)" />}
          title="À regarder plus tard"
          action={(
            <button className="chip" onClick={onOpenWatchlist}>
              Tout voir ({filteredWatchlist.length})
            </button>
          )}
        >
          <div className="card-grid">
            {filteredWatchlist.slice(0, 6).map((anime) => card(anime, anime.id || anime.url))}
          </div>
        </Shelf>
      )}

      {isBrowsingHome && filteredRecentAnimes.length > 0 && (
        <Shelf icon={<History size={18} color="var(--accent-cyan)" />} title="Récemment consultés">
          <div className="card-grid">
            {filteredRecentAnimes.slice(0, 6).map((anime, idx) => card(anime, anime.id || idx))}
          </div>
        </Shelf>
      )}

      {isBrowsingHome && filteredRandomSuggestions.length > 0 && (
        <Shelf
          icon={<Sparkles size={18} color="#E3B341" />}
          title="Découvertes"
          action={onRollRandom && (
            <button className="chip" onClick={onRollRandom}>
              <Shuffle size={14} /> Tirer au sort
            </button>
          )}
        >
          <div className="card-grid">
            {filteredRandomSuggestions.slice(0, 6).map((anime, idx) => card(anime, anime.id || idx))}
          </div>
        </Shelf>
      )}

      <Shelf
        title={
          // No count while loading: it would still be the previous search's
          searchQuery ? `Résultats pour "${searchQuery}"${isLoading ? '' : ` (${filteredResults.length})`}` : 'Catalogue complet'
        }
      >
        {/* Skeleton here only: the shelves above stay visible while the catalogue reloads */}
        {isLoading ? (
          <div className="card-grid">
            {[...Array(12)].map((_, i) => <AnimeCardSkeleton key={i} />)}
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
              Essayez un autre mot-clé ou actualisez le catalogue (icône en haut à droite) pour synchroniser les sources.
            </p>
          </div>
        ) : (
          <>
            <div className="card-grid">
              {catalogue.visible.map((anime, index) => card(anime, anime.id || index))}
            </div>
            {catalogue.hasMore && (
              // Observed to load the next page; also a plain button where IntersectionObserver is missing
              <div ref={catalogue.sentinelRef} style={{ display: 'flex', justifyContent: 'center' }}>
                <button className="chip" onClick={catalogue.showMore}>Afficher plus</button>
              </div>
            )}
          </>
        )}
      </Shelf>
    </div>
  );
}
