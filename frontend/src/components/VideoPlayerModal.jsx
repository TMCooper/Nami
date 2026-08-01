import React, { useState, useEffect, useRef } from 'react';
import Hls from 'hls.js';
import { X, Play, Pause, SkipForward, Download, Maximize, Volume2, VolumeX, List, Loader2 } from 'lucide-react';

export default function VideoPlayerModal({ anime, season, episode, episodes, onClose, onDownloadEpisode, onSelectNextEpisode }) {
  const videoRef = useRef(null);
  const [streamInfo, setStreamInfo] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPlaying, setIsPlaying] = useState(true);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [showEpisodeDrawer, setShowEpisodeDrawer] = useState(false);

  useEffect(() => {
    if (!episode) return;
    setIsLoading(true);

    const embedUrl = episode.embed_url || episode.url;

    fetch(`/api/resolve?embed_url=${encodeURIComponent(embedUrl)}&source=${anime?.source || 'anime_sama'}`)
      .then((res) => res.json())
      .then((data) => {
        setStreamInfo(data);
      })
      .catch((err) => console.error("Error resolving stream:", err))
      .finally(() => setIsLoading(false));
  }, [episode, anime]);

  // HLS stream setup
  useEffect(() => {
    if (!streamInfo?.stream_url || !videoRef.current) return;

    let hls;
    const video = videoRef.current;
    let targetStream = streamInfo.stream_url;

    // Use stream proxy if needed for CORS/Referer
    const proxiedUrl = `/api/proxy/stream?url=${encodeURIComponent(targetStream)}`;

    if (Hls.isSupported() && (streamInfo.stream_type === 'm3u8' || targetStream.includes('.m3u8'))) {
      hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true,
      });
      hls.loadSource(proxiedUrl);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => setIsPlaying(false));
      });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = proxiedUrl;
      video.play().catch(() => setIsPlaying(false));
    } else {
      video.src = proxiedUrl;
      video.play().catch(() => setIsPlaying(false));
    }

    return () => {
      if (hls) hls.destroy();
    };
  }, [streamInfo]);

  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play();
      }
      setIsPlaying(!isPlaying);
    }
  };

  const toggleFullscreen = () => {
    if (videoRef.current) {
      if (videoRef.current.requestFullscreen) {
        videoRef.current.requestFullscreen();
      }
    }
  };

  const currentEpIndex = episodes ? episodes.findIndex((e) => e.num === episode.num || e.title === episode.title) : -1;
  const hasNextEp = episodes && currentEpIndex !== -1 && currentEpIndex < episodes.length - 1;

  const handleEnded = () => {
    if (hasNextEp && onSelectNextEpisode) {
      onSelectNextEpisode(episodes[currentEpIndex + 1]);
    }
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
      {/* Top Controls Bar */}
      <div style={{
        padding: '16px 24px',
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff' }}>
            {anime?.title} — {season} — {episode?.title || `Épisode ${episode?.num}`}
          </h3>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {episodes && episodes.length > 1 && (
            <button
              className="btn btn-secondary"
              onClick={() => setShowEpisodeDrawer(!showEpisodeDrawer)}
            >
              <List size={16} /> Épisodes
            </button>
          )}
          <button
            className="btn btn-secondary"
            onClick={() => onDownloadEpisode(anime?.title, season, episode)}
          >
            <Download size={16} /> Télécharger
          </button>
          <button className="btn btn-icon btn-secondary" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
      </div>

      {/* Main Video Display */}
      <div style={{ flex: 1, position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#000' }}>
        {isLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', color: 'var(--text-muted)' }}>
            <Loader2 className="animate-spin" size={40} color="var(--primary)" />
            <span>Résolution du flux vidéo en cours...</span>
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
          <p style={{ color: 'var(--accent-pink)' }}>Impossible de charger la vidéo pour cet épisode.</p>
        )}

        {/* Next Episode Floating Overlay when nearing end or stopped */}
        {hasNextEp && !isLoading && (
          <button
            className="btn btn-primary"
            style={{
              position: 'absolute',
              bottom: '80px',
              right: '24px',
              zIndex: 30,
              boxShadow: '0 0 20px rgba(0,240,255,0.4)'
            }}
            onClick={() => onSelectNextEpisode(episodes[currentEpIndex + 1])}
          >
            <SkipForward size={16} /> Épisode Suivant
          </button>
        )}
      </div>

      {/* Episode Switcher Drawer */}
      {showEpisodeDrawer && episodes && (
        <div className="glass-modal" style={{
          position: 'absolute',
          top: '70px',
          right: '24px',
          width: '320px',
          maxHeight: 'calc(100vh - 100px)',
          overflowY: 'auto',
          borderRadius: 'var(--radius-md)',
          padding: '16px',
          zIndex: 30
        }}>
          <h4 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '12px' }}>Liste des Épisodes</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {episodes.map((ep, idx) => (
              <button
                key={idx}
                className={`btn ${(ep.num === episode.num || ep.title === episode.title) ? 'btn-primary' : 'btn-secondary'}`}
                style={{ justifyContent: 'flex-start', fontSize: '0.85rem' }}
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
