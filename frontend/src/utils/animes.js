// Same as the backend slug_of (last path segment, lowercased)
export const slugOf = (url) => {
  try {
    const p = new URL(url).pathname.replace(/\/+$/, '');
    return p ? p.split('/').pop().toLowerCase() : '';
  } catch {
    return '';
  }
};

// Identity keys of an anime: its id and its primary source entry (ids can change, entries do not)
export const animeKeys = (anime) => {
  const keys = [];
  if (anime?.id) keys.push(`k:${anime.id}`);
  const slug = slugOf(anime?.url);
  if (anime?.source && slug) keys.push(`e:${anime.source}:${slug}`);
  return keys;
};

export const sameAnime = (a, b) => {
  const keys = new Set(animeKeys(a));
  return animeKeys(b).some((k) => keys.has(k));
};

// What history writes need to link a record to its entity (null without an entity id)
export const animeRef = (details) => (details?.id ? {
  id: details.id,
  title: details.title || '',
  source: details.source || '',
  url: details.url || '',
  entry_title: details.entry_title || details.sources?.[0]?.title || details.title || '',
  banner: details.banner || null,
  trailer: details.trailer || null
} : null);

export const watchlistPayload = (anime) => ({
  id: anime.id || '',
  title: anime.title || '',
  alt_titles: anime.alt_titles || [],
  cover: anime.cover || '',
  cover_fallbacks: anime.cover_fallbacks || [],
  banner: anime.banner || null,
  trailer: anime.trailer || null,
  source: anime.source || '',
  url: anime.url || '',
  entry_title: anime.entry_title || anime.sources?.[0]?.title || anime.title || '',
  sources: anime.sources || []
});

// '12 min', '1 h 05', "moins d'une minute"
export const formatRemaining = (sec) => {
  const mins = Math.round((sec || 0) / 60);
  if (mins >= 60) return `${Math.floor(mins / 60)} h ${String(mins % 60).padStart(2, '0')}`;
  return mins >= 1 ? `${mins} min` : "moins d'une minute";
};

export const formatRelativeDate = (timestamp) => {
  if (!timestamp) return 'Récemment';
  const now = Date.now() / 1000;
  const diffSec = Math.max(0, now - timestamp);
  if (diffSec < 60) return "À l'instant";
  if (diffSec < 3600) return `Il y a ${Math.floor(diffSec / 60)} min`;
  if (diffSec < 86400) return `Il y a ${Math.floor(diffSec / 3600)} h`;
  if (diffSec < 172800) return "Hier";
  return `Il y a ${Math.floor(diffSec / 86400)} jours`;
};
