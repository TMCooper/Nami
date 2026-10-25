import React, { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';
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
import { findHistoryEntries } from '../utils/titles';

const FINISHED_RATIO = 0.85;
const HOST_WAIT_MS = 6000; // shelf resume: how long a stream-less stored host waits for the other hosts

// "Finished" as the server sees it (_finished): an explicit mark after the last play wins,
// and a rewatch in progress (watched stays true) is resumable again
const isFinished = (e) => {
  const ratio = e.duration_sec > 0 ? e.position_sec / e.duration_sec : 0;
  if (e.watched_at != null && e.watched_at >= (e.played_at || 0)) return Boolean(e.watched);
  if (e.played_at != null) return ratio >= FINISHED_RATIO;
  return Boolean(e.watched) || ratio >= FINISHED_RATIO;
};

// Entity context of a history write (the server links the record and remembers the next episode with it)
const historyContext = (s) => ({
  anime: s.context?.anime || null,
  season_key: s.context?.seasonKey || null,
  source: s.context?.source || null,
  version: s.context?.version || null,
  ep_title: s.epTitle || null,
  next_ep: s.nextEp ? { ep_id: String(s.nextEp.num || s.nextEp.title || ''), title: s.nextEp.title || '' } : null,
  link_via: s.context?.via === 'resume' ? 'resume' : null
});

export default function VideoPlayerModal({
  currentUser,
  animeTitle,
  cover,
  season,
  episode,
  episodes,
  initialTime = 0,
  initialFilePath = null,
  context = null,
  autoResume = false,
  fallbackPlayers = null,
  onClose,
  onDownloadEpisode,
  onSelectNextEpisode
}) {
  const videoRef = useRef(null);
  const containerRef = useRef(null);
  const progressBarRef = useRef(null);
  const controlsTimeoutRef = useRef(null);
  const contextRef = useRef(context);
  contextRef.current = context;
  const fallbackPlayersRef = useRef(fallbackPlayers);
  fallbackPlayersRef.current = fallbackPlayers;
  const identityRef = useRef(null); // the episode on screen, see the identity layout effect
  const sampleRef = useRef(null); // last position sample, with the identity it was taken for
  const samplingRef = useRef(false); // false until the current source reports its own metadata
  const pendingSeekRef = useRef(0); // shelf resume position not reached yet
  const hlsRef = useRef(null); // attached hls.js instance, destroyed on an episode switch
  const localSrcRef = useRef(null); // local stream URL last assigned to the video (video.src is normalized)
  const playingEmbedRef = useRef(null); // { key, embed }: host whose stream actually played the episode
  const hostWaitRef = useRef(null); // { timer, shown } while a stream-less stored host waits for the host list

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
  const episodeKey = `${animeTitle}\u0000${season}\u0000${epId}`;

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

  // Offer to resume a stored position. Its own effect: host and source switches must not prompt again.
  // A shelf resume (autoResume) seeks by itself and never prompts.
  useEffect(() => {
    setShowResumePrompt(false);
    if (!animeTitle || !episode || autoResume) return;
    if (initialTime > 10) {
      setResumeTime(initialTime);
      setShowResumePrompt(true);
      return;
    }
    let cancelled = false;
    fetch('/api/history', { headers: { 'X-User-ID': userId } })
      .then((res) => res.json())
      .then((data) => {
        if (cancelled) return;
        // Every key the variant may be stored under (legacy keys included), else the player's own;
        // among them, the resumable entry played last
        const keys = contextRef.current?.historyKeys?.length ? contextRef.current.historyKeys : [{ title: animeTitle, season }];
        const ep = findHistoryEntries(data, keys)
          .map(({ season: s, record }) => record.episodes?.[`${s}:${epId}`])
          .filter((e) => e && e.position_sec > 10 && !isFinished(e))
          .sort((a, b) => (b.played_at || b.last_watched_at || 0) - (a.played_at || a.last_watched_at || 0))[0];
        if (ep) {
          setResumeTime(ep.position_sec);
          setShowResumePrompt(true);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [episode, animeTitle, season, epId, userId, initialTime, autoResume]);

  // Shows a resolution result: { data, embed }
  const showResolved = (shown) => {
    setStreamInfo(shown.data);
    setShownEmbed(shown.embed);
    setIsLoading(false);
  };

  const cancelHostWait = () => {
    if (hostWaitRef.current) clearTimeout(hostWaitRef.current.timer);
    hostWaitRef.current = null;
  };

  // Shelf resume whose season list (and with it the other hosts) has not arrived yet.
  // VoirAnime episodes get their hosts from their own page (players effect), never from that list.
  const awaitsHostList = () => {
    const pageUrl = episode?.embed_url || episode?.url || '';
    return autoResume && !contextRef.current && fallbackPlayersRef.current == null
      && !episode?.players?.length && !playersRef.current.length && !pageUrl.includes('voir-anime');
  };

  // Resolve the online stream
  useEffect(() => {
    if (!animeTitle || !episode) return;
    setStreamInfo(null); // Clear previous stream

    if (activeSourceType === 'local' && (localFile || episode.file_path || initialFilePath)) {
      setIsLoading(false);
    } else {
      setIsLoading(true);
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
          // Saved with the progress, so a resume opens it first (keyed: a late answer for the previous episode is ignored)
          if (data.stream_url) playingEmbedRef.current = { key: episodeKey, embed: embedUrl };
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
            if (awaitsHostList()) {
              // The other hosts come with the season list: an iframe shown now could not seek and would be
              // torn down when they arrive. Keep loading for a while and let the list decide (fallbackPlayers effect).
              hostWaitRef.current = {
                shown,
                timer: setTimeout(() => {
                  hostWaitRef.current = null;
                  showResolved(firstIframeRef.current || shown);
                }, HOST_WAIT_MS)
              };
              return;
            }
            shown = firstIframeRef.current || shown;
          }
          showResolved(shown);
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
    return () => {
      cancelled = true;
      cancelHostWait();
    };
  }, [episode, animeTitle, season, epId, activeSourceType, selectedEmbed]);

  // Host fallbacks of a resumed Anime-Sama episode, merged in once the season list arrives (playback is not restarted).
  // [] means no list is coming (unlinked record, failed lookup).
  useEffect(() => {
    if (!fallbackPlayers || episode?.players?.length) return;
    if (fallbackPlayers.length) {
      setPlayers(fallbackPlayers);
      playersRef.current = fallbackPlayers;
    }
    const next = fallbackPlayers.find((p) => !triedEmbedsRef.current.has(p.embed_url));
    const waiting = hostWaitRef.current;
    if (waiting) {
      // The stored host has no stream and was waiting for this list: try the others, else show its iframe
      cancelHostWait();
      if (next) setSelectedEmbed(next.embed_url);
      else showResolved(firstIframeRef.current || waiting.shown);
      return;
    }
    if (next && !userPickedRef.current && !isLoading && !streamInfo?.stream_url && activeSourceType !== 'local') {
      setSelectedEmbed(next.embed_url); // the stored host failed: try the others now
    }
  }, [fallbackPlayers]);

  // Setup video source (Local disk stream vs HLS / MP4 online)
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let hls = null;
    let onCanPlay = null; // removed by the cleanup: a superseded source must never start playing again

    const tryPlay = () => {
      video.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
    };

    // Same episode, new source (host pick, local/online toggle, HLS fallback): it starts at 0, so it seeks to where
    // the old one was. sampleRef is null right after an episode switch, so this only acts within an episode.
    const carryPosition = () => {
      const pos = sampleRef.current?.pos || 0;
      if (pos > 5 && !pendingSeekRef.current) {
        pendingSeekRef.current = pos;
        samplingRef.current = false;
      }
    };

    if (activeSourceType === 'local' && localFile) {
      const localStreamUrl = `/api/stream/local?file_path=${encodeURIComponent(localFile)}`;
      // Compared with the URL last assigned: video.src is normalized (an apostrophe becomes %27) and never matches
      if (localSrcRef.current !== localStreamUrl) {
        carryPosition();
        localSrcRef.current = localStreamUrl;
        video.src = localStreamUrl;
        video.load();
      }
      setIsLoading(false);

      onCanPlay = () => {
        tryPlay();
        video.removeEventListener('canplay', onCanPlay);
      };
      video.addEventListener('canplay', onCanPlay);
      tryPlay();
    } else if (streamInfo?.stream_url) {
      const targetStream = streamInfo.stream_url;
      const proxiedUrl = `/api/proxy/stream?url=${encodeURIComponent(targetStream)}`;
      localSrcRef.current = null; // the local file (if any) is replaced

      if (Hls.isSupported() && (streamInfo.stream_type === 'm3u8' || targetStream.includes('.m3u8'))) {
        carryPosition();
        hls = new Hls({ enableWorker: true, lowLatencyMode: true });
        hlsRef.current = hls;
        hls.loadSource(proxiedUrl);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          setIsLoading(false);
          tryPlay();
        });
        hls.on(Hls.Events.ERROR, (_, data) => {
          if (data.fatal) {
            console.warn("HLS fatal error, falling back to direct play:", data);
            carryPosition();
            video.src = proxiedUrl;
            video.load();
            setIsLoading(false);
            tryPlay();
          }
        });
      } else {
        carryPosition();
        video.src = proxiedUrl;
        video.load();
        onCanPlay = () => {
          setIsLoading(false);
          tryPlay();
          video.removeEventListener('canplay', onCanPlay);
        };
        video.addEventListener('canplay', onCanPlay);
        tryPlay();
      }
    }

    return () => {
      // Already destroyed (and its media detached) when the episode switched
      if (hls && hlsRef.current === hls) {
        hls.destroy();
        hlsRef.current = null;
      }
      if (onCanPlay) video.removeEventListener('canplay', onCanPlay);
    };
  }, [activeSourceType, localFile, streamInfo]);

  // Real-time time & buffer updates
  const handleTimeUpdate = () => {
    if (!videoRef.current || isScrubbing) return;
    setCurrentTime(videoRef.current.currentTime);

    const v = videoRef.current;
    // Nothing is sampled while a resume seek is pending: position ~0 must never overwrite the stored one
    const p = pendingSeekRef.current;
    if (p && v.currentTime >= p - 2) pendingSeekRef.current = 0;
    if (samplingRef.current && !pendingSeekRef.current && Number.isFinite(v.duration) && v.duration > 0 && v.currentTime > 5) {
      sampleRef.current = { ...identityRef.current, pos: v.currentTime, dur: v.duration, savedPos: sampleRef.current?.savedPos };
    }

    // Update buffered end
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
      const v = videoRef.current;
      setDuration(v.duration || 0);
      v.volume = volume;
      v.muted = isMuted;
      v.playbackRate = playbackSpeed;
      samplingRef.current = true; // from now on this source's time belongs to the episode on screen
      // Shelf resume: seek straight to the stored position
      const target = pendingSeekRef.current;
      if (target > 0 && Number.isFinite(v.duration) && target < v.duration - 5) {
        v.currentTime = target;
        setCurrentTime(target);
      } else if (target > 0) {
        pendingSeekRef.current = 0; // cannot seek there (past this file's end, or no duration): sampling must not stay blocked
      }
    }
  };

  // Saves the last sample with the identity it was taken for (a plain function: it only reads refs).
  // Returns the request (never rejected), so the close can wait for the final save.
  const flushSample = (keepalive = false) => {
    const s = sampleRef.current;
    if (!s || s.pos === s.savedPos) return Promise.resolve();
    s.savedPos = s.pos;
    return fetch('/api/history/progress', {
      method: 'POST',
      keepalive,
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': s.userId
      },
      body: JSON.stringify({
        user_id: s.userId,
        anime_title: s.animeTitle,
        season: s.season,
        ep_id: s.epId,
        position_sec: s.pos,
        duration_sec: s.dur,
        cover: s.cover,
        embed_url: s.embedUrl,
        file_path: s.localFile,
        ...historyContext(s)
      })
    }).catch(() => {});
  };

  // Periodic progress saving (every 5s), plus on pause, hidden tab, episode switch and close
  useEffect(() => {
    const interval = setInterval(() => {
      if (videoRef.current && !videoRef.current.paused) flushSample();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === 'hidden') flushSample(true);
    };
    document.addEventListener('visibilitychange', onHide);
    return () => document.removeEventListener('visibilitychange', onHide);
  }, []);

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

  // Identity of the episode on screen: every position sample carries the one it was taken for
  useLayoutEffect(() => {
    const episodeUrl = episode?.embed_url || episode?.url || '';
    const playing = playingEmbedRef.current?.key === episodeKey ? playingEmbedRef.current.embed : '';
    identityRef.current = {
      userId,
      animeTitle,
      season,
      epId,
      cover: cover || '',
      // The host that actually streamed, so a resume opens it first; VoirAnime keeps its episode page
      // (its players and the history links are read from it)
      embedUrl: (!episodeUrl.includes('voir-anime') && playing) || episodeUrl,
      localFile: localFile || '',
      epTitle: episode?.synthetic_title ? '' : (episode?.title || ''),
      context,
      // Only a complete season list knows which episode comes next
      nextEp: context?.fullSeason && hasNextEp ? episodes[currentEpIndex + 1] : null
    };
  });

  // Episode switch and close. Under StrictMode's mount/unmount/mount, sampleRef is still null: nothing is sent.
  useLayoutEffect(() => {
    samplingRef.current = false; // samples start with this episode's own metadata
    sampleRef.current = null;
    pendingSeekRef.current = autoResume && initialTime > 0 ? initialTime : 0;
    playingEmbedRef.current = null;
    // The previous source must neither report time nor start playing again for this episode: detached, not only paused.
    // This runs before the passive effects, which attach this episode's source.
    if (hlsRef.current) {
      hlsRef.current.destroy(); // detaches its media
      hlsRef.current = null;
    }
    const v = videoRef.current;
    if (v) {
      v.pause();
      if (v.hasAttribute('src')) {
        v.removeAttribute('src');
        v.load();
      }
    }
    localSrcRef.current = null;
    return () => flushSample(true); // last sample of the previous episode
  }, [episodeKey]);

  const handleEnded = () => {
    flushSample();
    // Either request may land first: both lead to "finished" (position >= 85 %, or the mark)
    const id = identityRef.current;
    fetch('/api/history/toggle-watched', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': id.userId
      },
      body: JSON.stringify({
        user_id: id.userId,
        anime_title: id.animeTitle,
        season: id.season,
        ep_id: id.epId,
        cover: id.cover,
        watched: true,
        ...historyContext(id)
      })
    }).catch(() => {});

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

          <button
            className="btn btn-icon btn-secondary"
            onClick={() => {
              onClose(flushSample(true)); // App reloads the shelves once this last save is stored
            }}
            title="Fermer le lecteur (Échap)"
          >
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
          onPause={() => {
            setIsPlaying(false);
            flushSample();
          }}
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
                // A hydrated list has int nums, a resumed episode a string one
                const isSelected = (ep.num != null && String(ep.num) === String(episode.num)) || ep.title === episode.title;
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
