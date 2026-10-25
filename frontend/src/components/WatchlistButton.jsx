import React from 'react';
import { BookmarkCheck, BookmarkPlus } from 'lucide-react';

export default function WatchlistButton({ active, onToggle, variant = 'icon', disabled = false, style = {} }) {
  const label = active ? 'Retirer de « À regarder plus tard »' : 'Ajouter à « À regarder plus tard »';
  // Cards open the anime on click: the bookmark must never do that
  const handleClick = (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (!disabled) onToggle();
  };

  if (variant === 'pill') {
    return (
      <button
        type="button"
        className={`btn ${active ? 'btn-success' : 'btn-secondary'}`}
        aria-label={label}
        aria-pressed={active}
        title={label}
        disabled={disabled}
        onClick={handleClick}
        style={{ fontSize: '0.82rem', padding: '7px 14px', minHeight: '36px', opacity: disabled ? 0.5 : 1, ...style }}
      >
        {active ? <BookmarkCheck size={15} /> : <BookmarkPlus size={15} />}
        {active ? 'Dans ma liste' : 'À regarder plus tard'}
      </button>
    );
  }

  // Above the catalogue hover overlay (auto z-index) and the source badges (zIndex 5)
  return (
    <button
      type="button"
      className={`card-action${active ? ' active' : ''}`}
      aria-label={label}
      aria-pressed={active}
      title={label}
      onClick={handleClick}
      style={{ position: 'absolute', top: '8px', right: '8px', zIndex: 6, ...style }}
    >
      {active ? <BookmarkCheck size={17} /> : <BookmarkPlus size={17} />}
    </button>
  );
}
