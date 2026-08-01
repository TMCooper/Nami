import React, { useState, useEffect } from 'react';
import { History, Play, CheckCircle2, RotateCcw } from 'lucide-react';

export default function HistoryView({ onSelectAnime, onPlayEpisode }) {
  const [historyData, setHistoryData] = useState({});
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetch('/api/history')
      .then((res) => res.json())
      .then((data) => setHistoryData(data || {}))
      .catch((err) => console.error("Error loading history:", err))
      .finally(() => setIsLoading(false));
  }, []);

  const historyEntries = Object.values(historyData).sort((a, b) => (b.last_updated || 0) - (a.last_updated || 0));

  const formatTime = (seconds) => {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  if (isLoading) {
    return (
      <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
        Chargement de l'historique...
      </div>
    );
  }

  if (historyEntries.length === 0) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '350px',
        gap: '12px',
        color: 'var(--text-muted)'
      }}>
        <History size={48} style={{ opacity: 0.3 }} />
        <h3 style={{ fontSize: '1.2rem', color: '#fff' }}>Aucun historique de visionnage</h3>
        <p style={{ fontSize: '0.88rem' }}>Les animes et épisodes que vous visionnez apparaîtront ici pour reprendre la lecture facilement.</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '24px 0', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <History size={20} color="var(--accent-cyan)" />
        <h2 style={{ fontSize: '1.3rem', fontWeight: 800 }}>Historique & Reprise de lecture</h2>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
        gap: '16px'
      }}>
        {historyEntries.map((item, idx) => {
          const episodes = item.episodes || {};
          const epKeys = Object.keys(episodes);
          const watchedCount = epKeys.filter((k) => episodes[k].watched).length;
          
          // Find last episode watched
          const lastEpKey = `${item.last_season}:${item.last_ep_id}`;
          const lastEpRecord = episodes[lastEpKey] || {};
          const progressPercent = lastEpRecord.duration_sec ? (lastEpRecord.position_sec / lastEpRecord.duration_sec) * 100 : 0;

          return (
            <div
              key={idx}
              className="surface-card"
              style={{
                padding: '16px',
                borderRadius: 'var(--radius-md)',
                display: 'flex',
                flexDirection: 'column',
                justify: 'space-between',
                gap: '12px',
                border: '1px solid var(--border-color)'
              }}
            >
              <div>
                <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff', marginBottom: '4px' }}>
                  {item.anime_title}
                </h3>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Dernier visionné : {item.last_season} — Épisode {item.last_ep_id}
                </p>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', color: 'var(--accent-green)', marginTop: '4px' }}>
                  <CheckCircle2 size={12} />
                  <span>{watchedCount} épisode(s) vu(s)</span>
                </div>
              </div>

              {/* Progress Bar */}
              {lastEpRecord.position_sec > 0 && !lastEpRecord.watched && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-dim)', marginBottom: '4px' }}>
                    <span>Progression</span>
                    <span>{formatTime(lastEpRecord.position_sec)} / {formatTime(lastEpRecord.duration_sec)}</span>
                  </div>
                  <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
                    <div style={{ width: `${Math.min(100, progressPercent)}%`, height: '100%', background: 'var(--accent-cyan)' }}></div>
                  </div>
                </div>
              )}

              {/* Resume Button */}
              <button
                className="btn btn-primary"
                style={{ width: '100%', fontSize: '0.82rem', padding: '8px' }}
                onClick={() => onPlayEpisode(
                  { title: item.anime_title, source: 'anime_sama', url: '' },
                  item.last_season,
                  { num: item.last_ep_id, title: `Épisode ${item.last_ep_id}` },
                  [{ num: item.last_ep_id, title: `Épisode ${item.last_ep_id}` }]
                )}
              >
                <RotateCcw size={14} /> Reprendre l'Épisode {item.last_ep_id}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
