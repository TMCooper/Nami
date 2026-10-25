import React, { useState } from 'react';
import { DEFAULT_EPISODE_THUMB } from '../utils/placeholders';

// 16:9 image ladder: each wide source in turn, then the portrait cover contained ("poster mode"), then the placeholder
export default function WideThumb({ sources = [], cover = '', alt = '', blur = false }) {
  // Restarts when the candidates change, so it survives React reusing the element for another item
  const key = `${sources.join('|')}|${cover}`;
  const [state, setState] = useState({ key, step: 0 });
  const step = state.key === key ? state.step : 0;
  const next = () => setState({ key, step: step + 1 });

  if (step < sources.length) {
    return (
      <img
        src={sources[step]}
        alt={alt}
        loading="lazy"
        decoding="async"
        onError={next}
        style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center' }}
      />
    );
  }

  if (step === sources.length && cover) {
    // A portrait cover is never cut into a band: shown whole, over a blurred copy of itself
    return (
      <div style={{ position: 'absolute', inset: 0, background: '#0F0F0F' }}>
        {blur && (
          <img
            src={cover}
            alt=""
            aria-hidden="true"
            loading="lazy"
            decoding="async"
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', filter: 'blur(16px) brightness(0.5)', transform: 'scale(1.15)' }}
          />
        )}
        <img
          src={cover}
          alt={alt}
          loading="lazy"
          decoding="async"
          onError={next}
          style={{ position: 'relative', width: '100%', height: '100%', objectFit: 'contain' }}
        />
      </div>
    );
  }

  return (
    <img
      src={DEFAULT_EPISODE_THUMB}
      alt={alt}
      decoding="async"
      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
    />
  );
}
