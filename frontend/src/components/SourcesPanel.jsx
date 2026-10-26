import React, { useEffect, useState } from 'react';
import { RefreshCw, Loader2 } from 'lucide-react';

const STATUS = {
  ok: { label: 'En ligne', color: 'var(--accent-green)' },
  api_down: { label: 'API arrêtée', color: '#ff6b6b' },
  site_unreachable: { label: 'Site injoignable', color: '#ff6b6b' },
  cloudflare: { label: 'Bloqué par Cloudflare', color: 'var(--accent-yellow)' },
  unknown: { label: 'Vérification…', color: 'var(--text-muted)' }
};

// State of each source (its API and the site behind it) with an on/off switch; VoirAnime can get a Cloudflare cookie
export default function SourcesPanel({ onChange }) {
  const [sources, setSources] = useState(null);
  const [isChecking, setIsChecking] = useState(false);
  const [cookie, setCookie] = useState('');
  const [cookieMsg, setCookieMsg] = useState('');

  const apply = (data) => {
    if (data && typeof data === 'object') {
      setSources(data);
      onChange?.(data);
    }
  };

  const load = (refresh = false) => {
    setIsChecking(true);
    fetch(`/api/sources?refresh=${refresh}`)
      .then((res) => res.json())
      .then(apply)
      .catch(() => {})
      .finally(() => setIsChecking(false));
  };

  useEffect(() => { load(false); }, []);

  const toggle = (key, enabled) => {
    fetch(`/api/sources/${key}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) })
      .then((res) => res.json())
      .then(apply)
      .catch(() => {});
  };

  const sendCookie = () => {
    setCookieMsg('Envoi…');
    fetch('/api/sources/voiranime/cookie', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cookie }) })
      .then(async (res) => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        apply(data);
        setCookie('');
        setCookieMsg('Cookie transmis à l\'API VoirAnime.');
      })
      .catch((err) => setCookieMsg(err.message || 'Échec de l\'envoi.'));
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '6px' }}>
        <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--primary)' }}>Sources</h4>
        <button className="btn btn-ghost" style={{ fontSize: '0.75rem', padding: '3px 10px' }} onClick={() => load(true)} disabled={isChecking}>
          {isChecking ? <Loader2 className="animate-spin" size={12} /> : <RefreshCw size={12} />} Vérifier
        </button>
      </div>

      {!sources ? (
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Vérification des sources…</p>
      ) : Object.entries(sources).map(([key, s]) => {
        const status = s.enabled ? (STATUS[s.status] || STATUS.unknown) : { label: 'Désactivée', color: 'var(--text-dim)' };
        return (
          <div key={key} className="surface-card" style={{ padding: '10px 12px', borderRadius: 'var(--radius-sm)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ width: '9px', height: '9px', borderRadius: '50%', background: status.color, flexShrink: 0 }} />
                <strong style={{ fontSize: '0.9rem' }}>{s.label}</strong>
                <span style={{ fontSize: '0.76rem', color: status.color }}>{status.label}</span>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', cursor: 'pointer' }}>
                <input type="checkbox" checked={s.enabled} onChange={(e) => toggle(key, e.target.checked)} style={{ width: '18px', height: '18px', accentColor: 'var(--primary)' }} />
                Activée
              </label>
            </div>
            {s.enabled && s.message && <p style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>{s.message}</p>}
            {key === 'voiranime' && s.enabled && s.status === 'cloudflare' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <p style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                  Ouvrez voir-anime.to dans votre navigateur, passez la vérification, puis copiez ici la valeur du cookie <code>cf_clearance</code>.
                </p>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <input className="input-field" style={{ flex: 1, minWidth: 0 }} value={cookie} onChange={(e) => setCookie(e.target.value)} placeholder="cf_clearance=…" />
                  <button className="btn btn-secondary" style={{ fontSize: '0.78rem' }} onClick={sendCookie} disabled={cookie.trim().length < 10}>Envoyer</button>
                </div>
                {cookieMsg && <p style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>{cookieMsg}</p>}
              </div>
            )}
          </div>
        );
      })}
      <p style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
        Une source arrêtée, injoignable ou désactivée est ignorée partout (recherche, fiches, vérification YoitsuWrap) au lieu de ralentir le site.
      </p>
    </div>
  );
}
