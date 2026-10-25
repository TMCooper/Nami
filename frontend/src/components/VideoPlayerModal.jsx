import React, { useState, useEffect, useRef, useCallback } from 'react';
import Hls from 'hls.js';
import { X, Play, Pause, SkipForward, Download, List, Loader2, RotateCcw, HardDrive, Wifi, Maximize, Volume2, VolumeX } from 'lucide-react';

export default function VideoPlayerModal({
  currentUser,
  animeTitle,
  cover,
  season,
  episode,
  episodes,
  initialTime = 0,
  initialFilePath = null,
  onClose,
  onDownloadEpisode,
  onSelectNextEpisode
}) {
  const videoRef = useRef(null);
  const containerRef = useRef(null);

  const [streamInfo, setStreamInfo] = useState(null);
  const [localFile, setLocalFile] = useState(initialFilePath);
  const [activeSourceType, setActiveSourceType] = useState(initialFilePath ? 'local' : 'online'); // 'local' | 'online'
  const [isLoading, setIsLoading] = useState(true);
  const [isPlaying, setIsPlaying] = useState(true);
  const [showEpisodeDrawer, setShowEpisodeDrawer] = useState(false);
  const [resumeTime, setResumeTime] = useState(initialTime || 0);
  const [showResumePrompt, setShowResumePrompt] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);

  const epId = String(episode?.num || episode?.title || '1');
  const userId = currentUser?.id || 'default';

  // Check if file is downloaded locally on disk
  useEffect(() => {
    if (initialFilePath) {
      setLocalFile(initialFilePath);
      setActiveSourceType('local');
      return;
    }

    if (!animeTitle || !season) return;

    fetch(`/api/episodes/download-status?anime_title=${encodeURIComponent(animeTitle)}&season=${encodeURIComponent(season)}`)
      .then((res) => res.json())
      .then((data) => {
        const statusMap = data.downloaded_episodes || {};
        if (statusMap[epId] && statusMap[epId].file_path) {
          setLocalFile(statusMap[epId].file_path);
          setActiveSourceType('local'); // default to local if downloaded
        } else {
          setLocalFile(null);
          setActiveSourceType('online');
        }
      })
      .catch(() => {
        setActiveSourceType('online');
      });
  }, [animeTitle, season, epId, initialFilePath]);

  // Fetch watch history to know if we should offer resume
  useEffect(() => {
    if (!animeTitle || !episode) return;
    setIsLoading(true);

    if (initialTime && initialTime > 10) {
      setResumeTime(initialTime);
      setShowResumePrompt(true);
    } else {
      fetch('/api/history', {
        headers: { 'X-User-ID': userId }
      })
        .then((res) => res.json())
        .then((data) => {
          const epRecord = data[animeTitle]?.episodes?.[`${season}:${epId}`];
          if (epRecord && epRecord.position_sec > 10 && !epRecord.watched) {
            setResumeTime(epRecord.position_sec);
            setShowResumePrompt(true);
          }
        })
        .catch(() => {});
    }

    const embedUrl = episode.embed_url || episode.url;
    if (embedUrl) {
      fetch(`/api/resolve?embed_url=${encodeURIComponent(embedUrl)}`)
        .then((res) => res.json())
        .then((data) => setStreamInfo(data))
        .catch((err) => console.error("Error resolving stream:", err))
        .finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, [episode, animeTitle, season, userId, epId, initialTime]);

  // Setup video source (Local disk stream vs HLS / MP4 online)
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let hls = null;

    if (activeSourceType === 'local' && localFile) {
      // Local streaming via Range partial content
      const localStreamUrl = `/api/stream/local?file_path=${encodeURIComponent(localFile)}`;
      video.src = localStreamUrl;
      video.play().catch(() => setIsPlaying(false));
    } else if (streamInfo?.stream_url) {
      const targetStream = streamInfo.stream_url;
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
    }

    return () => {
      if (hls) hls.destroy();
    };
  }, [activeSourceType, localFile, streamInfo]);

  // Periodic progress saving (every 5s)
  useEffect(() => {
    const interval = setInterval(() => {
      if (videoRef.current && !videoRef.current.paused) {
        const currentPos = videoRef.current.currentTime;
        const totalDur = videoRef.current.duration;
        if (currentPos > 5 && totalDur > 0) {
          fetch('/api/history/progress', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-User-ID': userId
            },
            body: JSON.stringify({
              user_id: userId,
              anime_title: animeTitle,
              season: season,
              ep_id: epId,
              position_sec: currentPos,
              duration_sec: totalDur,
              cover: cover || '',
              embed_url: episode?.embed_url || episode?.url || '',
              file_path: localFile || ''
            })
          }).catch(() => {});
        }
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [animeTitle, season, epId, userId, cover, episode, localFile]);

  // Keyboard navigation shortcuts
  const handleKeyDown = useCallback((e) => {
    if (!videoRef.current) return;
    const v = videoRef.current;

    switch (e.code) {
      case 'Space':
        e.preventDefault();
        if (v.paused) {
          v.play();
          setIsPlaying(true);
        } else {
          v.pause();
          setIsPlaying(false);
        }
        break;
      case 'ArrowLeft':
        e.preventDefault();
        v.currentTime = Math.max(0, v.currentTime - 10);
        break;
      case 'ArrowRight':
        e.preventDefault();
        v.currentTime = Math.min(v.duration || 99999, v.currentTime + 10);
        break;
      case 'ArrowUp':
        e.preventDefault();
        v.volume = Math.min(1, v.volume + 0.1);
        break;
      case 'ArrowDown':
        e.preventDefault();
        v.volume = Math.max(0, v.volume - 0.1);
        break;
      case 'KeyF':
        e.preventDefault();
        if (document.fullscreenElement) {
          document.exitFullscreen().catch(() => {});
        } else if (containerRef.current) {
          containerRef.current.requestFullscreen().catch(() => {});
        }
        break;
      case 'KeyM':
        e.preventDefault();
        v.muted = !v.muted;
        break;
      default:
        break;
    }
  }, []);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const handleApplyResume = () => {
    if (videoRef.current && resumeTime > 0) {
      videoRef.current.currentTime = resumeTime;
    }
    setShowResumePrompt(false);
  };

  const handleSpeedChange = (speed) => {
    setPlaybackSpeed(speed);
    if (videoRef.current) {
      videoRef.current.playbackRate = speed;
    }
  };

  const currentEpIndex = episodes ? episodes.findIndex((e) => e.num === episode.num || e.title === episode.title) : -1;
  const hasNextEp = episodes && currentEpIndex !== -1 && currentEpIndex < episodes.length - 1;

  const handleEnded = () => {
    fetch('/api/history/toggle-watched', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': userId
      },
      body: JSON.stringify({
        user_id: userId,
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
    <div
      ref={containerRef}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 60,
        background: '#000',
        display: 'flex',
        flexDirection: 'column'
      }}
    >
      {/* Top Header Overlay */}
      <div style={{
        padding: '14px 24px',
        background: 'linear-gradient(to bottom, rgba(0,0,0,0.95), rgba(0,0,0,0.6) 70%, transparent)',
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
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>
            {animeTitle} — {season} — {episode?.title || `Épisode ${episode?.num}`}
          </h3>
          {localFile && (
            <span className="badge" style={{ background: 'rgba(46, 160, 67, 0.25)', color: '#3FB950', border: '1px solid rgba(46, 160, 67, 0.4)' }}>
              💾 Fichier Local
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Source Switcher if local file exists */}
          {localFile && (
            <button
              className="btn btn-secondary"
              style={{ fontSize: '0.78rem', padding: '5px 10px' }}
              onClick={() => setActiveSourceType(prev => prev === 'local' ? 'online' : 'local')}
            >
              {activeSourceType === 'local' ? (
                <><HardDrive size={13} color="#3FB950" /> Mode Local</>
              ) : (
                <><Wifi size={13} color="#58A6FF" /> Mode M3U8 Web</>
              )}
            </button>
          )}

          {/* Speed Selector */}
          <select
            value={playbackSpeed}
            onChange={(e) => handleSpeedChange(parseFloat(e.target.value))}
            style={{
              background: 'rgba(255,255,255,0.1)',
              color: '#fff',
              border: '1px solid rgba(255,255,255,0.2)',
              borderRadius: 'var(--radius-sm)',
              padding: '4px 8px',
              fontSize: '0.8rem',
              cursor: 'pointer'
            }}
          >
            <option value="0.75" style={{ background: '#161B22' }}>0.75x</option>
            <option value="1" style={{ background: '#161B22' }}>1.0x</option>
            <option value="1.25" style={{ background: '#161B22' }}>1.25x</option>
            <option value="1.5" style={{ background: '#161B22' }}>1.5x</option>
            <option value="2" style={{ background: '#161B22' }}>2.0x</option>
          </select>

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

      {/* Main Video Viewport */}
      <div style={{ flex: 1, position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#000' }}>
        {isLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px', color: 'var(--text-muted)' }}>
            <Loader2 className="animate-spin" size={36} color="var(--primary)" />
            <span style={{ fontSize: '0.9rem' }}>Préparation du flux de lecture...</span>
          </div>
        ) : (activeSourceType === 'local' && localFile) || streamInfo?.stream_url ? (
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
          <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
            <p>Impossible de charger le flux vidéo pour cet épisode.</p>
          </div>
        )}

        {/* Smart Resume Prompt Notification */}
        {showResumePrompt && (
          <div style={{
            position: 'absolute',
            bottom: '80px',
            left: '24px',
            background: 'rgba(22, 27, 34, 0.95)',
            border: '1px solid var(--accent-cyan)',
            backdropFilter: 'blur(10px)',
            borderRadius: 'var(--radius-md)',
            padding: '12px 18px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            zIndex: 30,
            boxShadow: '0 8px 24px rgba(0,0,0,0.6)'
          }}>
            <div>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Reprendre où vous en étiez ?</p>
              <p style={{ fontSize: '0.92rem', fontWeight: 700, color: '#fff' }}>À {formatTime(resumeTime)}</p>
            </div>
            <button className="btn btn-primary" style={{ padding: '6px 12px', fontSize: '0.8rem' }} onClick={handleApplyResume}>
              <RotateCcw size={13} /> Reprendre
            </button>
            <button className="btn btn-icon btn-secondary" style={{ width: '26px', height: '26px' }} onClick={() => setShowResumePrompt(false)}>
              <X size={14} />
            </button>
          </div>
        )}

        {/* Episode Selector Drawer Overlay */}
        {showEpisodeDrawer && episodes && (
          <div style={{
            position: 'absolute',
            top: '60px',
            right: 0,
            bottom: 0,
            width: '320px',
            background: 'rgba(13, 17, 23, 0.95)',
            borderLeft: '1px solid var(--border-color)',
            backdropFilter: 'blur(12px)',
            zIndex: 25,
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#fff' }}>Liste des épisodes</h4>
              <button className="btn btn-icon btn-secondary" style={{ width: '26px', height: '26px' }} onClick={() => setShowEpisodeDrawer(false)}>
                <X size={14} />
              </button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {episodes.map((ep, idx) => {
                const isSelected = ep.num === episode.num || ep.title === episode.title;
                return (
                  <button
                    key={idx}
                    className={`btn ${isSelected ? 'btn-primary' : 'btn-secondary'}`}
                    style={{
                      justifyContent: 'flex-start',
                      padding: '8px 12px',
                      fontSize: '0.85rem'
                    }}
                    onClick={() => {
                      if (onSelectNextEpisode) onSelectNextEpisode(ep);
                      setShowEpisodeDrawer(false);
                    }}
                  >
                    <Play size={12} style={{ marginRight: '6px' }} />
                    {ep.title || `Épisode ${ep.num || idx + 1}`}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
