import React, { useState, useEffect, useRef, useCallback } from 'react';
import Hls from 'hls.js';
import {
  X,
  Play,
  Pause,
  SkipForward,
  RotateCcw,
  RotateCw,
  Download,
  List,
  Loader2,
  HardDrive,
  Wifi,
  Maximize,
  Minimize,
  Volume2,
  VolumeX,
  Volume1
} from 'lucide-react';
import { findStoredRecord } from '../utils/titles';

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
  const progressBarRef = useRef(null);
  const controlsTimeoutRef = useRef(null);

  const [streamInfo, setStreamInfo] = useState(null);
  // Every player (host) of the episode; selectedEmbed is the player being resolved (picked by the
  // user, or the next one tried automatically), shownEmbed the one actually displayed
  const [players, setPlayers] = useState(episode?.players || []);
  const [selectedEmbed, setSelectedEmbed] = useState(null);
  const [shownEmbed, setShownEmbed] = useState(null);
  const playersRef = useRef(players);
  playersRef.current = players;
  const triedEmbedsRef = useRef(new Set());
  const userPickedRef = useRef(false);
  const firstIframeRef = useRef(null); // best-ranked player without a direct stream, kept as last resort
  const [localFile, setLocalFile] = useState(initialFilePath || episode?.file_path || null);
  const [activeSourceType, setActiveSourceType] = useState((initialFilePath || episode?.file_path) ? 'local' : 'online');
  const [isLoading, setIsLoading] = useState(!initialFilePath && !episode?.file_path);
  const [isPlaying, setIsPlaying] = useState(true);
  const [showEpisodeDrawer, setShowEpisodeDrawer] = useState(false);
  const [resumeTime, setResumeTime] = useState(initialTime || 0);
  const [showResumePrompt, setShowResumePrompt] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Playback & Seek state
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [bufferedEnd, setBufferedEnd] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [isScrubbing, setIsScrubbing] = useState(false);
  const [hoverTime, setHoverTime] = useState(null);
  const [hoverPosition, setHoverPosition] = useState(0);
  const [areControlsVisible, setAreControlsVisible] = useState(true);

  const epId = String(episode?.num || episode?.title || '1');
  const userId = currentUser?.id || 'default';

  // Format time (mm:ss or hh:mm:ss)
  const formatTime = (seconds) => {
    if (isNaN(seconds) || seconds < 0) return '00:00';
    const totalSecs = Math.floor(seconds);
    const hrs = Math.floor(totalSecs / 3600);
    const mins = Math.floor((totalSecs % 3600) / 60);
    const secs = totalSecs % 60;
    if (hrs > 0) {
      return `${hrs}:${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}`;
    }
    return `${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  // Check if file is downloaded locally on disk
  useEffect(() => {
    if (initialFilePath || episode?.file_path) {
      const targetPath = initialFilePath || episode?.file_path;
      setLocalFile(targetPath);
      setActiveSourceType('local');
      setIsLoading(false);
      return;
    }

    setLocalFile(null);
    setActiveSourceType('online');

    if (!animeTitle || !season) return;

    fetch(`/api/episodes/download-status?anime_title=${encodeURIComponent(animeTitle)}&season=${encodeURIComponent(season)}`)
      .then((res) => res.json())
      .then((data) => {
        const statusMap = data.downloaded_episodes || {};
        if (statusMap[epId] && statusMap[epId].file_path) {
          setLocalFile(statusMap[epId].file_path);
          setActiveSourceType('local');
        } else {
          setLocalFile(null);
          setActiveSourceType('online');
        }
      })
      .catch(() => {
        setActiveSourceType('online');
      });
  }, [animeTitle, season, epId, initialFilePath, episode]);

  // Players list: inline for Anime-Sama episodes, fetched from the episode page for VoirAnime
  useEffect(() => {
    setSelectedEmbed(null);
    setShownEmbed(null);
    triedEmbedsRef.current = new Set();
    userPickedRef.current = false;
    firstIframeRef.current = null;
    if (episode?.players?.length) {
      setPlayers(episode.players);
      return;
    }
    setPlayers([]);
    const pageUrl = episode?.embed_url || episode?.url || '';
    if (!pageUrl.includes('voir-anime')) return;
    let cancelled = false;
    fetch(`/api/episode/players?url=${encodeURIComponent(pageUrl)}`)
      .then((res) => (res.ok ? res.json() : { players: [] }))
      .then((data) => { if (!cancelled) setPlayers(data.players || []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [episode]);

  // Fetch watch history to know if we should offer resume, and resolve online stream
  useEffect(() => {
    if (!animeTitle || !episode) return;
    setStreamInfo(null); // Clear previous stream

    if (activeSourceType === 'local' && (localFile || episode.file_path || initialFilePath)) {
      setIsLoading(false);
    } else {
      setIsLoading(true);
    }

    if (initialTime && initialTime > 10) {
      setResumeTime(initialTime);
      setShowResumePrompt(true);
    } else {
      fetch('/api/history', {
        headers: { 'X-User-ID': userId }
      })
        .then((res) => res.json())
        .then((data) => {
          const epRecord = findStoredRecord(data, animeTitle)?.episodes?.[`${season}:${epId}`];
          if (epRecord && epRecord.position_sec > 10 && !epRecord.watched) {
            setResumeTime(epRecord.position_sec);
            setShowResumePrompt(true);
          }
        })
        .catch(() => {});
    }

    let cancelled = false; // a newer episode / player choice supersedes this resolution
    const embedUrl = selectedEmbed || episode.embed_url || episode.url;
    if (embedUrl && activeSourceType !== 'local') {
      triedEmbedsRef.current.add(embedUrl);
      fetch(`/api/resolve?embed_url=${encodeURIComponent(embedUrl)}`)
        .then((res) => res.json())
        .then((data) => {
          if (cancelled) return;
          if (data.iframe_url) triedEmbedsRef.current.add(data.iframe_url);
          let shown = { data, embed: data.iframe_url || embedUrl };
          if (!data.stream_url && !userPickedRef.current) {
            // No direct stream from this host: try the next player, and if none has one,
            // show the best-ranked player's iframe (never override a player the user picked)
            if (!firstIframeRef.current && data.iframe_url) firstIframeRef.current = shown;
            const next = playersRef.current.find((p) => !triedEmbedsRef.current.has(p.embed_url));
            if (next) {
              setSelectedEmbed(next.embed_url);
              return;
            }
            shown = firstIframeRef.current || shown;
          }
          setStreamInfo(shown.data);
          setShownEmbed(shown.embed);
          setIsLoading(false);
        })
        .catch((err) => {
          if (cancelled) return;
          console.error("Error resolving stream:", err);
          setIsLoading(false);
        });
    } else if (embedUrl) {
      // Background resolve stream in case user toggles from local to online stream
      fetch(`/api/resolve?embed_url=${encodeURIComponent(embedUrl)}`)
        .then((res) => res.json())
        .then((data) => { if (!cancelled) setStreamInfo(data); })
        .catch(() => {});
    }
    return () => { cancelled = true; };
  }, [episode, animeTitle, season, userId, epId, initialTime, activeSourceType, selectedEmbed]);

  // Setup video source (Local disk stream vs HLS / MP4 online)
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let hls = null;

    const tryPlay = () => {
      video.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
    };

    if (activeSourceType === 'local' && localFile) {
      const localStreamUrl = `/api/stream/local?file_path=${encodeURIComponent(localFile)}`;
      if (video.src !== window.location.origin + localStreamUrl) {
        video.src = localStreamUrl;
        video.load();
      }
      setIsLoading(false);

      const onCanPlay = () => {
        tryPlay();
        video.removeEventListener('canplay', onCanPlay);
      };
      video.addEventListener('canplay', onCanPlay);
      tryPlay();
    } else if (streamInfo?.stream_url) {
      const targetStream = streamInfo.stream_url;
      const proxiedUrl = `/api/proxy/stream?url=${encodeURIComponent(targetStream)}`;

      if (Hls.isSupported() && (streamInfo.stream_type === 'm3u8' || targetStream.includes('.m3u8'))) {
        hls = new Hls({ enableWorker: true, lowLatencyMode: true });
        hls.loadSource(proxiedUrl);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          setIsLoading(false);
          tryPlay();
        });
        hls.on(Hls.Events.ERROR, (_, data) => {
          if (data.fatal) {
            console.warn("HLS fatal error, falling back to direct play:", data);
            video.src = proxiedUrl;
            video.load();
            setIsLoading(false);
            tryPlay();
          }
        });
      } else {
        video.src = proxiedUrl;
        video.load();
        const onCanPlay = () => {
          setIsLoading(false);
          tryPlay();
          video.removeEventListener('canplay', onCanPlay);
        };
        video.addEventListener('canplay', onCanPlay);
        tryPlay();
      }
    }

    return () => {
      if (hls) hls.destroy();
    };
  }, [activeSourceType, localFile, streamInfo]);

  // Real-time time & buffer updates
  const handleTimeUpdate = () => {
    if (!videoRef.current || isScrubbing) return;
    setCurrentTime(videoRef.current.currentTime);

    // Update buffered end
    const v = videoRef.current;
    if (v.buffered && v.buffered.length > 0) {
      for (let i = 0; i < v.buffered.length; i++) {
        if (v.buffered.start(i) <= v.currentTime && v.currentTime <= v.buffered.end(i)) {
          setBufferedEnd(v.buffered.end(i));
          break;
        }
      }
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration || 0);
      videoRef.current.volume = volume;
      videoRef.current.muted = isMuted;
      videoRef.current.playbackRate = playbackSpeed;
    }
  };

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

  // Auto-hide controls timer on mouse idle
  const handleMouseMove = () => {
    setAreControlsVisible(true);
    if (controlsTimeoutRef.current) {
      clearTimeout(controlsTimeoutRef.current);
    }
    if (isPlaying) {
      controlsTimeoutRef.current = setTimeout(() => {
        setAreControlsVisible(false);
      }, 2500);
    }
  };

  useEffect(() => {
    return () => {
      if (controlsTimeoutRef.current) clearTimeout(controlsTimeoutRef.current);
    };
  }, []);

  // Keyboard navigation shortcuts
  const handleKeyDown = useCallback((e) => {
    if (!videoRef.current) return;
    const v = videoRef.current;

    switch (e.code) {
      case 'Space':
        e.preventDefault();
        togglePlayPause();
        break;
      case 'ArrowLeft':
        e.preventDefault();
        seekRelative(-10);
        break;
      case 'ArrowRight':
        e.preventDefault();
        seekRelative(10);
        break;
      case 'ArrowUp':
        e.preventDefault();
        changeVolume(Math.min(1, volume + 0.1));
        break;
      case 'ArrowDown':
        e.preventDefault();
        changeVolume(Math.max(0, volume - 0.1));
        break;
      case 'KeyF':
        e.preventDefault();
        toggleFullscreen();
        break;
      case 'KeyM':
        e.preventDefault();
        toggleMute();
        break;
      default:
        break;
    }
  }, [volume, isPlaying]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const togglePlayPause = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      v.play();
      setIsPlaying(true);
    } else {
      v.pause();
      setIsPlaying(false);
    }
    setAreControlsVisible(true);
  };

  const seekRelative = (deltaSecs) => {
    if (!videoRef.current) return;
    const target = Math.max(0, Math.min(videoRef.current.duration || 99999, videoRef.current.currentTime + deltaSecs));
    videoRef.current.currentTime = target;
    setCurrentTime(target);
    setAreControlsVisible(true);
  };

  // Mouse seekbar interaction
  const calculateSeekTime = (clientX) => {
    if (!progressBarRef.current || !duration) return 0;
    const rect = progressBarRef.current.getBoundingClientRect();
    const pos = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return pos * duration;
  };

  const handleProgressBarClick = (e) => {
    if (!videoRef.current || !duration) return;
    const targetTime = calculateSeekTime(e.clientX);
    videoRef.current.currentTime = targetTime;
    setCurrentTime(targetTime);
  };

  const handleProgressBarMouseMove = (e) => {
    if (!progressBarRef.current || !duration) return;
    const rect = progressBarRef.current.getBoundingClientRect();
    const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    setHoverPosition(pos * 100);
    setHoverTime(pos * duration);
  };

  const handleProgressBarMouseLeave = () => {
    setHoverTime(null);
  };

  const changeVolume = (newVol) => {
    setVolume(newVol);
    if (newVol === 0) {
      setIsMuted(true);
    } else {
      setIsMuted(false);
    }
    if (videoRef.current) {
      videoRef.current.volume = newVol;
      videoRef.current.muted = newVol === 0;
    }
  };

  const toggleMute = () => {
    const nextMuted = !isMuted;
    setIsMuted(nextMuted);
    if (videoRef.current) {
      videoRef.current.muted = nextMuted;
    }
  };

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  const handleApplyResume = () => {
    if (videoRef.current && resumeTime > 0) {
      videoRef.current.currentTime = resumeTime;
      setCurrentTime(resumeTime);
    }
    setShowResumePrompt(false);
  };

  const handleSpeedChange = (speed) => {
    setPlaybackSpeed(speed);
    if (videoRef.current) {
      videoRef.current.playbackRate = speed;
    }
  };

  const currentEpIndex = (episodes && episode)
    ? episodes.findIndex((e) => {
        if (episode.embed_url && e.embed_url && episode.embed_url === e.embed_url) return true;
        if (episode.url && e.url && episode.url === e.url) return true;
        if (episode.file_path && e.file_path && episode.file_path === e.file_path) return true;
        if (episode.num != null && e.num != null && String(episode.num) === String(e.num)) return true;
        if (episode.title && e.title && episode.title === e.title) return true;
        return false;
      })
    : -1;
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

  const isVideoLoaded = (activeSourceType === 'local' && localFile) || streamInfo?.stream_url;
  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0;
  const bufferedPercent = duration > 0 ? (bufferedEnd / duration) * 100 : 0;

  return (
    <div
      ref={containerRef}
      onMouseMove={handleMouseMove}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        width: '100vw',
        height: '100vh',
        maxWidth: '100vw',
        maxHeight: '100vh',
        overflow: 'hidden',
        boxSizing: 'border-box',
        margin: 0,
        padding: 0,
        zIndex: 9999,
        background: '#000',
        display: 'flex',
        flexDirection: 'column',
        cursor: areControlsVisible ? 'default' : 'none'
      }}
    >
      {/* Top Header Overlay */}
      <div style={{
        padding: '16px 24px',
        background: 'linear-gradient(to bottom, rgba(0,0,0,0.9), rgba(0,0,0,0.4) 70%, transparent)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 30,
        opacity: areControlsVisible ? 1 : 0,
        pointerEvents: areControlsVisible ? 'auto' : 'none',
        transition: 'opacity 0.25s ease'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
          <h3 style={{
            fontSize: '1rem',
            fontWeight: 700,
            color: '#fff',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis'
          }}>
            {animeTitle} — {season} — {episode?.title || `Épisode ${episode?.num}`}
          </h3>
          {activeSourceType === 'local' && (localFile || episode?.file_path) ? (
            <span className="badge" style={{ background: 'rgba(46, 160, 67, 0.25)', color: '#3FB950', border: '1px solid rgba(46, 160, 67, 0.4)', flexShrink: 0, display: 'flex', alignItems: 'center', gap: '5px' }}>
              <HardDrive size={12} /> Médiathèque Locale
            </span>
          ) : (
            <span className="badge" style={{ background: 'rgba(88, 166, 255, 0.25)', color: '#58A6FF', border: '1px solid rgba(88, 166, 255, 0.4)', flexShrink: 0, display: 'flex', alignItems: 'center', gap: '5px' }}>
              <Wifi size={12} /> En ligne{streamInfo?.host ? ` · ${streamInfo.host}` : ''}{streamInfo?.stream_type ? ` (${streamInfo.stream_type.toUpperCase()})` : ''}
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          {/* Player (host) selector: another host when the current one fails */}
          {activeSourceType !== 'local' && players.length > 1 && (
            <select
              className="input-field"
              style={{ fontSize: '0.78rem', padding: '5px 8px', maxWidth: '180px' }}
              value={Math.max(0, players.findIndex((p) => p.embed_url === (shownEmbed || selectedEmbed)))}
              onChange={(e) => {
                userPickedRef.current = true;
                setSelectedEmbed(players[Number(e.target.value)]?.embed_url || null);
              }}
              title="Changer de lecteur"
            >
              {players.map((p, idx) => (
                <option key={p.embed_url} value={idx}>Lecteur {idx + 1} · {p.host}</option>
              ))}
            </select>
          )}

          {/* Source Switcher — only show when both local AND online stream exist */}
          {localFile && streamInfo?.stream_url && (
            <button
              className="btn btn-secondary"
              style={{ fontSize: '0.78rem', padding: '5px 10px' }}
              onClick={() => setActiveSourceType(prev => prev === 'local' ? 'online' : 'local')}
              title="Basculer entre la lecture sur disque et le flux M3U8 web"
            >
              {activeSourceType === 'local' ? (
                <><HardDrive size={13} color="#3FB950" /> Disque Local</>
              ) : (
                <><Wifi size={13} color="#58A6FF" /> M3U8 Web</>
              )}
            </button>
          )}

          {episodes && episodes.length > 1 && (
            <button className="btn btn-secondary" style={{ fontSize: '0.8rem', padding: '5px 10px' }} onClick={() => setShowEpisodeDrawer(!showEpisodeDrawer)}>
              <List size={14} /> Épisodes
            </button>
          )}

          <button className="btn btn-secondary" style={{ fontSize: '0.8rem', padding: '5px 10px' }} onClick={() => onDownloadEpisode(animeTitle, season, episode)}>
            <Download size={14} /> Télécharger
          </button>

          <button className="btn btn-icon btn-secondary" onClick={onClose} title="Fermer le lecteur (Échap)">
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Main Video Viewport */}
      <div
        style={{
          flex: 1,
          width: '100%',
          height: '100%',
          maxWidth: '100%',
          maxHeight: '100%',
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          background: '#000'
        }}
        onClick={togglePlayPause}
      >
        {/* Video Player (Always mounted in DOM so videoRef is immediately available) */}
        <video
          ref={videoRef}
          style={{
            width: '100%',
            height: '100%',
            maxWidth: '100%',
            maxHeight: '100%',
            objectFit: 'contain',
            display: streamInfo?.iframe_url && !isVideoLoaded ? 'none' : 'block'
          }}
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onEnded={handleEnded}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
        />

        {/* Loading Overlay */}
        {isLoading && (
          <div style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '10px',
            color: 'var(--text-muted)',
            background: 'rgba(0,0,0,0.85)',
            zIndex: 15
          }}>
            <Loader2 className="animate-spin" size={38} color="var(--primary)" />
            <span style={{ fontSize: '0.9rem' }}>Préparation du flux de lecture...</span>
          </div>
        )}

        {/* Fallback iframe if only iframe is available */}
        {!isVideoLoaded && streamInfo?.iframe_url && !isLoading && (
          <iframe
            src={streamInfo.iframe_url}
            style={{ width: '100%', height: '100%', maxWidth: '100%', maxHeight: '100%', border: 'none' }}
            allowFullScreen
            title="Anime Player"
          />
        )}

        {/* Fallback error if nothing is loadable */}
        {!isVideoLoaded && !streamInfo?.iframe_url && !isLoading && (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', zIndex: 10 }}>
            <p>Impossible de charger le flux vidéo pour cet épisode.</p>
          </div>
        )}

        {/* Smart Resume Prompt Notification */}
        {showResumePrompt && (
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              position: 'absolute',
              bottom: '100px',
              left: '24px',
              background: 'rgba(22, 27, 34, 0.95)',
              border: '1px solid var(--accent-cyan)',
              backdropFilter: 'blur(10px)',
              borderRadius: 'var(--radius-md)',
              padding: '12px 18px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              zIndex: 40,
              boxShadow: '0 8px 24px rgba(0,0,0,0.6)'
            }}
          >
            <div>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Reprendre la lecture ?</p>
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
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              position: 'absolute',
              top: '60px',
              right: 0,
              bottom: 0,
              width: '320px',
              maxWidth: '85vw',
              background: 'rgba(13, 17, 23, 0.96)',
              borderLeft: '1px solid var(--border-color)',
              backdropFilter: 'blur(14px)',
              zIndex: 35,
              padding: '16px',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px'
            }}
          >
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

      {/* Interactive Bottom Control Bar & Scrub Bar (For Video Player) */}
      {isVideoLoaded && (
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            zIndex: 30,
            background: 'linear-gradient(to top, rgba(0,0,0,0.92) 0%, rgba(0,0,0,0.6) 60%, transparent)',
            padding: '24px 24px 16px 24px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            opacity: areControlsVisible ? 1 : 0,
            pointerEvents: areControlsVisible ? 'auto' : 'none',
            transition: 'opacity 0.25s ease'
          }}
        >
          {/* Interactive Mouse Scrub / Progress Bar */}
          <div
            ref={progressBarRef}
            onClick={handleProgressBarClick}
            onMouseMove={handleProgressBarMouseMove}
            onMouseLeave={handleProgressBarMouseLeave}
            style={{
              width: '100%',
              height: '8px',
              background: 'rgba(255, 255, 255, 0.2)',
              borderRadius: '4px',
              position: 'relative',
              cursor: 'pointer',
              transition: 'height 0.15s ease'
            }}
          >
            {/* Buffered Progress Bar */}
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                bottom: 0,
                width: `${Math.min(100, bufferedPercent)}%`,
                background: 'rgba(255, 255, 255, 0.35)',
                borderRadius: '4px',
                pointerEvents: 'none'
              }}
            />

            {/* Current Played Progress Bar */}
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                bottom: 0,
                width: `${Math.min(100, progressPercent)}%`,
                background: 'linear-gradient(90deg, #ff416c, #ff4b2b)',
                borderRadius: '4px',
                pointerEvents: 'none'
              }}
            />

            {/* Scrubber Thumb */}
            <div
              style={{
                position: 'absolute',
                top: '50%',
                left: `${Math.min(100, progressPercent)}%`,
                transform: 'translate(-50%, -50%)',
                width: '14px',
                height: '14px',
                borderRadius: '50%',
                background: '#fff',
                boxShadow: '0 0 8px rgba(255,75,43,0.8)',
                pointerEvents: 'none'
              }}
            />

            {/* Hover Tooltip Timestamp */}
            {hoverTime !== null && (
              <div
                style={{
                  position: 'absolute',
                  bottom: '16px',
                  left: `${hoverPosition}%`,
                  transform: 'translateX(-50%)',
                  background: 'rgba(13, 17, 23, 0.95)',
                  border: '1px solid rgba(255, 255, 255, 0.2)',
                  color: '#fff',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  padding: '3px 8px',
                  borderRadius: '4px',
                  pointerEvents: 'none',
                  whiteSpace: 'nowrap'
                }}
              >
                {formatTime(hoverTime)}
              </div>
            )}
          </div>

          {/* Bottom Controls Row */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
            {/* Left Controls: Play, Skip -10s, Skip +10s, Volume, Time */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <button
                className="btn btn-icon btn-primary"
                onClick={togglePlayPause}
                style={{ width: '36px', height: '36px', borderRadius: '50%' }}
                title={isPlaying ? "Pause (Espace)" : "Lire (Espace)"}
              >
                {isPlaying ? <Pause size={16} fill="#fff" /> : <Play size={16} fill="#fff" />}
              </button>

              <button
                className="btn btn-icon btn-secondary"
                onClick={() => seekRelative(-10)}
                style={{ width: '32px', height: '32px' }}
                title="Reculer de 10 secondes (Flèche Gauche)"
              >
                <RotateCcw size={15} />
              </button>

              <button
                className="btn btn-icon btn-secondary"
                onClick={() => seekRelative(10)}
                style={{ width: '32px', height: '32px' }}
                title="Avancer de 10 secondes (Flèche Droite)"
              >
                <RotateCw size={15} />
              </button>

              {/* Volume & Mute */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: '6px' }}>
                <button
                  className="btn btn-icon btn-secondary"
                  onClick={toggleMute}
                  style={{ width: '30px', height: '30px' }}
                  title={isMuted ? "Activer le son (M)" : "Couper le son (M)"}
                >
                  {isMuted || volume === 0 ? <VolumeX size={15} /> : volume < 0.5 ? <Volume1 size={15} /> : <Volume2 size={15} />}
                </button>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={isMuted ? 0 : volume}
                  onChange={(e) => changeVolume(parseFloat(e.target.value))}
                  style={{
                    width: '70px',
                    height: '4px',
                    cursor: 'pointer',
                    accentColor: '#ff4b2b'
                  }}
                  title={`Volume : ${Math.round((isMuted ? 0 : volume) * 100)}%`}
                />
              </div>

              {/* Time Display */}
              <span style={{ fontSize: '0.84rem', color: '#fff', fontWeight: 600, marginLeft: '8px' }}>
                {formatTime(currentTime)} <span style={{ color: 'var(--text-muted)' }}>/ {formatTime(duration)}</span>
              </span>
            </div>

            {/* Right Controls: Speed, Next Ep, Fullscreen */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
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
                title="Vitesse de lecture"
              >
                <option value="0.75" style={{ background: '#161B22' }}>0.75x</option>
                <option value="1" style={{ background: '#161B22' }}>1.0x</option>
                <option value="1.25" style={{ background: '#161B22' }}>1.25x</option>
                <option value="1.5" style={{ background: '#161B22' }}>1.5x</option>
                <option value="2" style={{ background: '#161B22' }}>2.0x</option>
              </select>

              {hasNextEp && onSelectNextEpisode && (
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: '0.8rem', padding: '5px 10px' }}
                  onClick={() => onSelectNextEpisode(episodes[currentEpIndex + 1])}
                  title="Épisode suivant"
                >
                  <SkipForward size={14} /> Suivant
                </button>
              )}

              <button
                className="btn btn-icon btn-secondary"
                onClick={toggleFullscreen}
                style={{ width: '32px', height: '32px' }}
                title={isFullscreen ? "Quitter plein écran (F)" : "Plein écran (F)"}
              >
                {isFullscreen ? <Minimize size={16} /> : <Maximize size={16} />}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
