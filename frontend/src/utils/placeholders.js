// Local (inline SVG) fallbacks: no third-party placeholder service, works offline.
const svg = (markup) => 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(markup);

const GRADIENTS = `
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#161B22"/>
      <stop offset="50%" stop-color="#0D1117"/>
      <stop offset="100%" stop-color="#090D12"/>
    </linearGradient>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#FF385C"/>
      <stop offset="100%" stop-color="#00B4D8"/>
    </linearGradient>
  </defs>`;

export const DEFAULT_ANIME_COVER = svg(`
<svg xmlns="http://www.w3.org/2000/svg" width="300" height="420" viewBox="0 0 300 420">${GRADIENTS}
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <circle cx="150" cy="180" r="48" fill="url(#g)" opacity="0.2"/>
  <polygon points="142,160 166,180 142,200" fill="#ffffff" opacity="0.9"/>
  <text x="150" y="248" text-anchor="middle" fill="#8B949E" font-family="system-ui, -apple-system, sans-serif" font-size="13" font-weight="700" letter-spacing="1.5">NAMI</text>
</svg>
`);

export const DEFAULT_EPISODE_THUMB = svg(`
<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">${GRADIENTS}
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <circle cx="160" cy="82" r="30" fill="url(#g)" opacity="0.2"/>
  <polygon points="153,70 170,82 153,94" fill="#ffffff" opacity="0.9"/>
  <text x="160" y="140" text-anchor="middle" fill="#8B949E" font-family="system-ui, -apple-system, sans-serif" font-size="11" font-weight="700" letter-spacing="1.5">NAMI</text>
</svg>
`);

export const DEFAULT_PAGE_IMAGE = svg(`
<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1200" viewBox="0 0 800 1200">${GRADIENTS}
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <text x="400" y="600" text-anchor="middle" fill="#8B949E" font-family="system-ui, -apple-system, sans-serif" font-size="28" font-weight="700">Image indisponible</text>
</svg>
`);

/**
 * onError handler that walks a fallback list once, then settles on the local placeholder.
 * Unlike comparing e.target.src (always absolute) with a relative URL, it cannot loop.
 */
export const imageFallback = (fallbacks = [], placeholder = DEFAULT_ANIME_COVER) => (e) => {
  const img = e.currentTarget;
  const candidates = fallbacks.filter(Boolean);
  // React reuses <img> elements across list items: restart when the fallback list changes
  const key = candidates.join('|');
  if (img.dataset.fallbackKey !== key) {
    img.dataset.fallbackKey = key;
    img.dataset.fallbackStep = '0';
  }
  const step = Number(img.dataset.fallbackStep || 0);
  img.dataset.fallbackStep = String(step + 1);
  if (step < candidates.length) {
    img.src = candidates[step];
  } else if (step === candidates.length) {
    img.src = placeholder;
  }
};
