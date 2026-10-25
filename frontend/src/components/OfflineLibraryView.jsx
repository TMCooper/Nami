import React, { useState, useEffect } from 'react';
import { HardDrive, Play, Folder, Film, Loader2, Sparkles, RefreshCw } from 'lucide-react';

export default function OfflineLibraryView({ onPlayEpisode }) {
  const [library, setLibrary] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchLibrary = () => {
    setIsLoading(true);
    fetch('/api/library/downloaded')
      .then((res) => res.json())
      .then((data) => setLibrary(data.library || []))
      .catch((err) => console.error("Error loading offline library:", err))
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    fetchLibrary();
  }, []);

  if (isLoading) {
    return (
      <div style={{ padding: '60px', textAlign: 'center', color: 'var(--text-muted)' }}>
        <Loader2 className="animate-spin" size={28} color="var(--primary)" style={{ margin: '0 auto 10px auto' }} />
        <span>Scan des fichiers téléchargés sur le disque...</span>
      </div>
    );
  }

  if (library.length === 0) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '400px',
        textAlign: 'center',
        gap: '14px',
        color: 'var(--text-muted)',
        padding: '24px'
      }}>
        <div style={{
          width: '64px',
          height: '64px',
          borderRadius: '50%',
          background: 'rgba(56, 139, 253, 0.1)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: '1px solid rgba(56, 139, 253, 0.2)'
        }}>
          <HardDrive size={30} color="#58A6FF" />
        </div>
        <h3 style={{ fontSize: '1.25rem', color: '#fff', fontWeight: 700 }}>Aucun anime téléchargé sur le disque</h3>
        <p style={{ maxWidth: '460px', fontSize: '0.88rem', lineHeight: '1.5' }}>
          Les épisodes que vous téléchargez sont automatiquement stockés sur votre disque hôte (dossier <code style={{ color: '#58A6FF' }}>/downloads</code>). Vous pourrez les lire ici même sans connexion Internet !
        </p>
      </div>
    );
  }

  return (
    <div style={{ padding: '24px 0', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <HardDrive size={22} color="#3FB950" />
          <h2 style={{ fontSize: '1.3rem', fontWeight: 800 }}>Médiathèque Locale Hors-Ligne</h2>
          <span className="badge" style={{ background: 'rgba(46, 160, 67, 0.2)', color: '#3FB950' }}>
            {library.length} série(s) disponible(s)
          </span>
        </div>
        <button className="btn btn-secondary" style={{ fontSize: '0.8rem', padding: '5px 12px' }} onClick={fetchLibrary}>
          <RefreshCw size={13} /> Re-scanner le disque
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {library.map((anime, idx) => (
          <div
            key={idx}
            className="surface-card"
            style={{
              padding: '18px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-color)',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '10px' }}>
              <div>
                <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#fff' }}>{anime.anime_title}</h3>
                <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  {anime.total_episodes} épisode(s) téléchargé(s)
                </span>
              </div>
            </div>

            {/* Seasons */}
            {anime.seasons.map((season, sIdx) => (
              <div key={sIdx} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.9rem', fontWeight: 700, color: 'var(--accent-cyan)' }}>
                  <Folder size={15} />
                  <span>{season.season_name}</span>
                </div>

                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                  gap: '10px'
                }}>
                  {season.episodes.map((ep, epIdx) => (
                    <div
                      key={epIdx}
                      style={{
                        background: '#0D1117',
                        border: '1px solid var(--border-color)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '10px 12px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '8px'
                      }}
                    >
                      <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff' }}>
                          Épisode {ep.num}
                        </span>
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          {ep.size_mb} Mo
                        </span>
                      </div>

                      <button
                        className="btn btn-primary"
                        style={{ padding: '5px 10px', fontSize: '0.78rem' }}
                        onClick={() => onPlayEpisode(
                          anime.anime_title,
                          season.season_name,
                          { num: ep.num, title: `Épisode ${ep.num}` },
                          season.episodes.map(e => ({ num: e.num, title: `Épisode ${e.num}` })),
                          '',
                          0,
                          ep.file_path
                        )}
                      >
                        <Play size={12} fill="#fff" /> Lire Local
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
