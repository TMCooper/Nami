// Same idea as the backend title keys: accents, case, punctuation and VF/VOSTFR tags ignored
export const normalizeTitle = (title) => (title || '')
  .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  .toLowerCase()
  .replace(/\((?:vf|vostfr)\)/g, ' ')
  .replace(/[^a-z0-9]+/g, ' ')
  .trim()
  .replace(/\s+(?:vf|vostfr)$/, '');

// Exactly the backend history key (normalize_title_key): a "... Vf" title is another record
export const titleKey = (title) => (title || '')
  .normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
  .toLowerCase()
  .replace(/[^\p{L}\p{N}]+/gu, ' ')
  .trim();

// History record stored under a title (the backend matches titles by key, not by exact spelling)
export const findStoredRecord = (history, title) => {
  const wanted = titleKey(title);
  if (!wanted) return null;
  const match = Object.entries(history || {}).find(([stored]) => titleKey(stored) === wanted);
  return match ? match[1] : null;
};

// Where the episodes of one season variant may be stored: [{ title, season, record }] for each
// (title, season name) pair the backend lists in history_keys (legacy keys included)
export const findHistoryEntries = (history, keys = []) => {
  const entries = [];
  const seen = new Set();
  keys.forEach(({ title, season }) => {
    const wanted = titleKey(title);
    Object.entries(history || {}).forEach(([stored, record]) => {
      const id = `${stored}\u0000${season}`;
      if (titleKey(stored) === wanted && !seen.has(id)) {
        seen.add(id);
        entries.push({ title: stored, season, record });
      }
    });
  });
  return entries;
};
