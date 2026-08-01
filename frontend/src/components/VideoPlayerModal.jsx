import React, { useState, useEffect, useRef } from 'react';
import Hls from 'hls.js';
import { X, Play, Pause, SkipForward, Download, List, Loader2, RotateCcw } from 'lucide-react';

export default function VideoPlayerModal({ animeTitle, season, episode, episodes, onClose, onDownloadEpisode, onSelectNextEpisode }) {
  const videoRef = useRef(null);
  const [streamInfo, setStreamInfo] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPlaying, setIsPlaying] = useState(true);
  const [showEpisodeDrawer, setShowEpisodeDrawer] = useState(false);
  const [resumeTime, setResumeTime] = useState(0);
  const [showResumePrompt, setShowResumePrompt] = useState(false);

  const epId = String(episode?.num || episode?.title || '1');

  // Fetch saved watch history for resume timestamp
  useEffect(() => {
    if (!animeTitle || !episode) return;
    setIsLoading(true);

    fetch('/api/history')
      .then((res) => res.json())
      .then((data) => {
        const epRecord = data[animeTitle]?.episodes?.[`${season}:${epId}`];
        if (epRecord && epRecord.position_sec > 10 && !epRecord.watched) {
          setResumeTime(epRecord.position_sec);
          setShowResumePrompt(true);
        }
      })
      .catch(() => {});

    const embedUrl = episode.embed_url || episode.url;

    fetch(`/api/resolve?embed_url=${encodeURIComponent(embedUrl)}`)
      .then((res) => res.json())
      .then((data) => setStreamInfo(data))
      .catch((err) => console.error("Error resolving stream:", err))
      .finally(() => setIsLoading(false));
  }, [episode, animeTitle, season]);

  // HLS stream setup
  useEffect(() => {
    if (!streamInfo?.stream_url || !videoRef.current) return;

    let hls;
    const video = videoRef.current;
    let targetStream = streamInfo.stream_url;
    const proxiedUrl = `/api/proxy/stream?url=${encodeURIComponent(targetStream)}`;

    if (Hls.isSupported() && (streamInfo.stream_type === 'm3u8' || targetStream.includes('.m3u8'))) {
      hls = new Hls({ enableWorker: true, lowLatencyMode: true });
      hls.loadSource(proxiedUrl);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => setIsPlaying(false));
      });
    } else {
      video.src = proxiedUrl;
      video.play().catch(() => setIsPlaying(false));
    }

    return () => {
      if (hls) hls.destroy();
    };
  }, [streamInfo]);

  // Periodic progress saving (every 5s)
  useEffect(() => {
    const interval = setInterval(() => {
      if (videoRef.current && !videoRef.current.paused) {
        const currentPos = videoRef.current.currentTime;
        const totalDur = videoRef.current.duration;
        if (currentPos > 5 && totalDur > 0) {
          fetch('/api/history/progress', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              anime_title: animeTitle,
              season: season,
              ep_id: epId,
              position_sec: currentPos,
              duration_sec: totalDur
            })
          }).catch(() => {});
        }
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [animeTitle, season, epId]);

  const handleApplyResume = () => {
    if (videoRef.current && resumeTime > 0) {
      videoRef.current.currentTime = resumeTime;
    }
    setShowResumePrompt(false);
  };

  const currentEpIndex = episodes ? episodes.findIndex((e) => e.num === episode.num || e.title === episode.title) : -1;
  const hasNextEp = episodes && currentEpIndex !== -1 && currentEpIndex < episodes.length - 1;

  const handleEnded = () => {
    // Mark as watched
    fetch('/api/history/toggle-watched', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        anime_title: animeTitle,
        season: season,
        ep_id: epId,
        watched: true
      })
    });

    if (hasNextEp && onSelectNextEpisode) {
      onSelectNextEpisode(episodes[currentEpIndex + 1]);
    }
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 60,
      background: '#000',
      display: 'flex',
      flexDirection: 'column'
    }}>
      {/* Top Header */}
      <div style={{
        padding: '14px 20px',
        background: 'linear-gradient(to bottom, rgba(0,0,0,0.9), transparent)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 20
      }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>
          {animeTitle} — {season} — {episode?.title || `Épisode ${episode?.num}`}
        </h3>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {episodes && episodes.length > 1 && (
            <button className="btn btn-secondary" style={{ fontSize: '0.8rem' }} onClick={() => setShowEpisodeDrawer(!showEpisodeDrawer)}>
              <List size={14} /> Épisodes
            </button>
          )}
          <button className="btn btn-secondary" style={{ fontSize: '0.8rem' }} onClick={() => onDownloadEpisode(animeTitle, season, episode)}>
            <Download size={14} /> Télécharger
          </button>
          <button className="btn btn-icon btn-secondary" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Main Video Screen */}
      <div style={{ flex: 1, position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#000' }}>
        {isLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px', color: 'var(--text-muted)' }}>
            <Loader2 className="animate-spin" size={32} color="var(--primary)" />
            <span style={{ fontSize: '0.9rem' }}>Résolution du flux...</span>
          </div>
        ) : streamInfo?.stream_url ? (
          <video
            ref={videoRef}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            controls
            onEnded={handleEnded}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
          />
        ) : streamInfo?.iframe_url ? (
          <iframe
            src={streamInfo.iframe_url}
            style={{ width: '100%', height: '100%', border: 'none' }}
            allowFullScreen
            title="Anime Player"
          />
        ) : (
          <p style={{ color: 'var(--primary)' }}>Erreur de chargement du lecteur.</p>
        )}

        {/* Resume Prompt Toast */}
        {showResumePrompt && (
          <div className="surface" style={{
            position: 'absolute',
            top: '70px',
            left: '50%',
            transform: 'translateX(-50%)',
            padding: '10px 18px',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            zIndex: 30,
            boxShadow: '0 4px 20px rgba(0,0,0,0.8)'
          }}>
            <span style={{ fontSize: '0.85rem' }}>Reprendre la lecture à <strong>{formatTime(resumeTime)}</strong> ?</span>
            <button className="btn btn-primary" style={{ padding: '4px 10px', fontSize: '0.78rem' }} onClick={handleApplyResume}>
              <RotateCcw size={12} /> Reprendre
            </button>
            <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: '0.78rem' }} onClick={() => setShowResumePrompt(false)}>
              Ignorer
            </button>
          </div>
        )}

        {/* Next Episode Button overlay */}
        {hasNextEp && !isLoading && (
          <button
            className="btn btn-primary"
            style={{
              position: 'absolute',
              bottom: '80px',
              right: '20px',
              zIndex: 30
            }}
            onClick={() => onSelectNextEpisode(episodes[currentEpIndex + 1])}
          >
            <SkipForward size={14} /> Épisode Suivant
          </button>
        )}
      </div>

      {/* Episode Switcher Drawer */}
      {showEpisodeDrawer && episodes && (
        <div className="surface" style={{
          position: 'absolute',
          top: '60px',
          right: '20px',
          width: '280px',
          maxHeight: 'calc(100vh - 90px)',
          overflowY: 'auto',
          borderRadius: 'var(--radius-sm)',
          padding: '14px',
          zIndex: 30
        }}>
          <h4 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '10px' }}>Liste des Épisodes</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {episodes.map((ep, idx) => (
              <button
                key={idx}
                className={`btn ${(ep.num === episode.num || ep.title === episode.title) ? 'btn-primary' : 'btn-secondary'}`}
                style={{ justifyContent: 'flex-start', fontSize: '0.82rem', padding: '6px 10px' }}
                onClick={() => {
                  onSelectNextEpisode(ep);
                  setShowEpisodeDrawer(false);
                }}
              >
                {ep.title || `Épisode ${ep.num}`}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
