import React, { useState, useEffect, useMemo } from 'react';
import {
  History,
  Play,
  CheckCircle2,
  RotateCcw,
  ExternalLink,
  Trash2,
  Search,
  Clock,
  Film,
  Check,
  X,
  Filter,
  HardDrive,
  Wifi,
  Loader2
} from 'lucide-react';
import WideThumb from './WideThumb';
import { formatRelativeDate } from '../utils/animes';

export default function HistoryView({ currentUser, resumingKey = null, onSelectAnime, onResumeEpisode }) {
  const [historyData, setHistoryData] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [searchFilter, setSearchFilter] = useState('');
  const [activeTab, setActiveTab] = useState('all'); // 'all', 'in_progress', 'completed'

  const userId = currentUser?.id || 'default';

  const fetchHistory = () => {
    setIsLoading(true);
    fetch('/api/history', {
      headers: { 'X-User-ID': userId }
    })
      .then((res) => res.json())
      .then((data) => setHistoryData(data || {}))
      .catch((err) => console.error("Error loading history:", err))
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    fetchHistory();
  }, [userId]);

  const handleDeleteItem = (animeTitle, epKey = null, e = null) => {
    if (e) e.stopPropagation();
    const query = epKey
      ? `anime_title=${encodeURIComponent(animeTitle)}&ep_key=${encodeURIComponent(epKey)}`
      : `anime_title=${encodeURIComponent(animeTitle)}`;
    
    fetch(`/api/history/item?${query}`, {
      method: 'DELETE',
      headers: { 'X-User-ID': userId }
    })
      .then((res) => res.json())
      .then(() => fetchHistory())
      .catch((err) => console.error("Error deleting history item:", err));
  };

  const handleClearAll = () => {
    if (window.confirm("Voulez-vous vraiment effacer tout votre historique de visionnage ?")) {
      fetch('/api/history/clear', {
        method: 'DELETE',
        headers: { 'X-User-ID': userId }
      })
        .then((res) => res.json())
        .then(() => fetchHistory())
        .catch((err) => console.error("Error clearing history:", err));
    }
  };

  const handleToggleWatched = (animeTitle, season, epId, isWatched, e = null) => {
    if (e) e.stopPropagation();
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
        ep_id: String(epId),
        watched: !isWatched
      })
    })
      .then(() => fetchHistory())
      .catch((err) => console.error("Error toggling watched:", err));
  };

  const formatTime = (seconds) => {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  // Same path as the home shelf: full season list, auto-advance, direct seek (no prompt); « Revoir » starts at 0
  const resumeKeyOf = (video) => `${video.animeTitle}:${video.epKey}`;
  const play = (video) => onResumeEpisode({
    key: resumeKeyOf(video),
    anime_title: video.animeTitle,
    season: video.season,
    episode_num: video.epId,
    episode_title: '',
    embed_url: video.embed_url,
    file_path: video.file_path,
    position_sec: video.watched ? 0 : video.position_sec,
    cover: video.animeCover,
    anime: video.anime,
    is_next: false
  });

  // Linked records open their entity directly, others go through the title lookup
  const openAnime = (video) => onSelectAnime(
    video.anime ? { ...video.anime, cover: video.animeCover } : { title: video.animeTitle, cover: video.animeCover }
  );

  // Flatten history items into individual watched video entries (YouTube style)
  const flattenedVideos = useMemo(() => {
    const list = [];
    Object.values(historyData).forEach((animeRecord) => {
      const animeTitle = animeRecord.anime_title || '';
      const animeCover = animeRecord.cover || '';
      const episodes = animeRecord.episodes || {};

      Object.entries(episodes).forEach(([epKey, epData]) => {
        // Season names may contain ':' (the episode id never does)
        const sep = epKey.lastIndexOf(':');
        const season = sep >= 0 ? epKey.slice(0, sep) : '';
        const epId = sep >= 0 ? epKey.slice(sep + 1) : epKey;
        const pos = epData.position_sec || 0;
        const dur = epData.duration_sec || 1440;
        const watched = epData.watched || false;
        const progress = dur > 0 ? (pos / dur) * 100 : 0;
        const lastWatched = epData.last_watched_at || animeRecord.last_updated || 0;
        const filePath = epData.file_path || null;
        const embedUrl = epData.embed_url || null;

        list.push({
          animeTitle,
          animeCover,
          epKey,
          season: season || animeRecord.last_season || 'Saison 1',
          epId: epId || animeRecord.last_ep_id || '1',
          position_sec: pos,
          duration_sec: dur,
          watched,
          progress_percent: Math.min(100, Math.max(0, progress)),
          last_watched_at: lastWatched,
          file_path: filePath,
          embed_url: embedUrl,
          anime: animeRecord.anime || null
        });
      });
    });

    list.sort((a, b) => b.last_watched_at - a.last_watched_at);
    return list;
  }, [historyData]);

  // Filter videos by search & tab
  const filteredVideos = useMemo(() => {
    return flattenedVideos.filter((video) => {
      if (searchFilter.trim()) {
        const query = searchFilter.toLowerCase().trim();
        const matchTitle = video.animeTitle.toLowerCase().includes(query)
          || (video.anime?.title || '').toLowerCase().includes(query);
        const matchEp = `épisode ${video.epId}`.includes(query) || video.season.toLowerCase().includes(query);
        if (!matchTitle && !matchEp) return false;
      }

      if (activeTab === 'in_progress') return !video.watched && video.position_sec > 10;
      if (activeTab === 'completed') return video.watched;
      return true;
    });
  }, [flattenedVideos, searchFilter, activeTab]);

  if (isLoading) {
    return (
      <div style={{ padding: '60px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
        <Clock className="animate-spin" size={24} style={{ margin: '0 auto 12px' }} />
        Chargement de votre historique...
      </div>
    );
  }

  return (
    <div style={{ padding: '24px 0', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* 1. Header Toolbar (YouTube Style) */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '16px',
        paddingBottom: '16px',
        borderBottom: '1px solid var(--border-color)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: '42px',
            height: '42px',
            borderRadius: '10px',
            background: 'linear-gradient(135deg, rgba(255, 0, 0, 0.15), rgba(88, 166, 255, 0.15))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '1px solid rgba(255, 255, 255, 0.1)'
          }}>
            <History size={22} color="#FF0000" />
          </div>
          <div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 800, color: '#fff', letterSpacing: '-0.02em', margin: 0 }}>
              Historique de visionnage
            </h2>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '2px 0 0 0' }}>
              {flattenedVideos.length} vidéo(s) • Profil de {currentUser?.username || 'Utilisateur'}
            </p>
          </div>
        </div>

        {/* Search & Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', width: '220px' }}>
            <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input
              type="text"
              className="input-field"
              placeholder="Rechercher..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              style={{
                width: '100%',
                padding: '6px 10px 6px 30px',
                fontSize: '0.82rem',
                borderRadius: 'var(--radius-full)'
              }}
            />
            {searchFilter && (
              <button
                onClick={() => setSearchFilter('')}
                style={{
                  position: 'absolute',
                  right: '8px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer'
                }}
              >
                <X size={12} />
              </button>
            )}
          </div>

          {flattenedVideos.length > 0 && (
            <button
              className="btn btn-secondary"
              onClick={handleClearAll}
              style={{ fontSize: '0.8rem', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '6px', color: '#ff6b6b' }}
              title="Supprimer tout l'historique"
            >
              <Trash2 size={13} /> Effacer tout
            </button>
          )}
        </div>
      </div>

      {/* Filter Tabs */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        <button
          className={`btn ${activeTab === 'all' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveTab('all')}
          style={{ fontSize: '0.78rem', padding: '5px 12px', borderRadius: 'var(--radius-full)' }}
        >
          Tous ({flattenedVideos.length})
        </button>
        <button
          className={`btn ${activeTab === 'in_progress' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveTab('in_progress')}
          style={{ fontSize: '0.78rem', padding: '5px 12px', borderRadius: 'var(--radius-full)' }}
        >
          En cours ({flattenedVideos.filter(v => !v.watched && v.position_sec > 10).length})
        </button>
        <button
          className={`btn ${activeTab === 'completed' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveTab('completed')}
          style={{ fontSize: '0.78rem', padding: '5px 12px', borderRadius: 'var(--radius-full)' }}
        >
          Terminés ({flattenedVideos.filter(v => v.watched).length})
        </button>
      </div>

      {/* Empty State */}
      {filteredVideos.length === 0 ? (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '320px',
          gap: '12px',
          color: 'var(--text-muted)'
        }}>
          <Film size={44} style={{ opacity: 0.25 }} />
          <h3 style={{ fontSize: '1.15rem', color: '#fff' }}>
            {searchFilter ? 'Aucun résultat trouvé' : 'Aucun historique de visionnage'}
          </h3>
          <p style={{ fontSize: '0.85rem', maxWidth: '400px', textAlign: 'center' }}>
            {searchFilter
              ? 'Aucun épisode ne correspond à votre recherche.'
              : 'Les vidéos que vous regardez apparaîtront automatiquement ici avec votre progression exacte.'}
          </p>
        </div>
      ) : (
        /* YouTube-Style Video List / Grid */
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '16px'
        }}>
          {filteredVideos.map((video, idx) => {
            const hasLocal = Boolean(video.file_path);
            const isResuming = resumingKey === resumeKeyOf(video); // waiting for its season list

            return (
              <div
                key={`${video.animeTitle}:${video.epKey}:${idx}`}
                className="surface-card animate-fade-in"
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '18px',
                  padding: '12px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-color)',
                  background: 'linear-gradient(145deg, rgba(22, 27, 34, 0.85), rgba(13, 17, 23, 0.85))',
                  alignItems: 'center',
                  transition: 'var(--transition)',
                  position: 'relative'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border-active)';
                  e.currentTarget.style.transform = 'translateX(4px)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border-color)';
                  e.currentTarget.style.transform = 'translateX(0)';
                }}
              >
                {/* 16:9 Thumbnail Box (Classic YouTube Preview) */}
                <div
                  style={{
                    position: 'relative',
                    width: '240px',
                    minWidth: '240px',
                    height: '135px',
                    borderRadius: 'var(--radius-sm)',
                    overflow: 'hidden',
                    background: '#0D1117',
                    cursor: 'pointer',
                    flexShrink: 0
                  }}
                  onClick={() => play(video)}
                >
                  <WideThumb
                    sources={[
                      video.file_path && `/api/stream/thumbnail?file_path=${encodeURIComponent(video.file_path)}`,
                      ...(video.anime?.wide_images || [])
                    ].filter(Boolean)}
                    cover={video.animeCover}
                    alt={video.animeTitle}
                  />

                  {/* Play Overlay */}
                  <div
                    style={{
                      position: 'absolute',
                      inset: 0,
                      background: 'rgba(0,0,0,0.35)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      opacity: 0,
                      transition: 'opacity 0.2s ease'
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.opacity = '1'}
                    onMouseLeave={(e) => e.currentTarget.style.opacity = '0'}
                  >
                    <div style={{
                      width: '42px',
                      height: '42px',
                      borderRadius: '50%',
                      background: '#FF0000',
                      color: '#fff',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      boxShadow: '0 4px 14px rgba(255, 0, 0, 0.4)'
                    }}>
                      <Play size={18} fill="#fff" style={{ marginLeft: '2px' }} />
                    </div>
                  </div>

                  {/* Video Duration / Time watched Badge */}
                  <div style={{
                    position: 'absolute',
                    bottom: '8px',
                    right: '8px',
                    background: 'rgba(0, 0, 0, 0.85)',
                    color: '#fff',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    letterSpacing: '0.02em',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}>
                    {formatTime(video.duration_sec)}
                  </div>

                  {/* Source indicator pill */}
                  <div style={{ position: 'absolute', top: '8px', left: '8px' }}>
                    {hasLocal ? (
                      <span className="badge" style={{ background: 'rgba(46, 160, 67, 0.85)', color: '#fff', padding: '2px 6px', fontSize: '0.65rem' }}>
                        <HardDrive size={10} /> Disque
                      </span>
                    ) : (
                      <span className="badge" style={{ background: 'rgba(88, 166, 255, 0.85)', color: '#fff', padding: '2px 6px', fontSize: '0.65rem' }}>
                        <Wifi size={10} /> M3U8
                      </span>
                    )}
                  </div>

                  {/* YouTube Red Progress Bar along bottom of thumbnail */}
                  {video.position_sec > 0 && (
                    <div style={{
                      position: 'absolute',
                      bottom: 0,
                      left: 0,
                      right: 0,
                      height: '4px',
                      background: 'rgba(255, 255, 255, 0.25)',
                      zIndex: 3
                    }}>
                      <div style={{
                        width: `${video.watched ? 100 : video.progress_percent}%`,
                        height: '100%',
                        background: '#FF0000',
                        boxShadow: '0 0 6px rgba(255, 0, 0, 0.8)'
                      }}></div>
                    </div>
                  )}
                </div>

                {/* Metadata Column (YouTube Style) */}
                <div style={{ flex: 1, minWidth: '220px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <h3
                        style={{
                          fontSize: '1.05rem',
                          fontWeight: 700,
                          color: '#fff',
                          margin: 0,
                          cursor: 'pointer',
                          lineHeight: 1.3
                        }}
                        onClick={() => play(video)}
                      >
                        {video.animeTitle} — {video.season} • Épisode {video.epId}
                      </h3>
                      
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
                        <span
                          style={{ fontSize: '0.85rem', color: 'var(--accent-cyan)', cursor: 'pointer', fontWeight: 600 }}
                          onClick={() => openAnime(video)}
                          title="Ouvrir la fiche de la série"
                        >
                          {video.anime?.title || video.animeTitle}
                        </span>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>•</span>
                        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          {formatRelativeDate(video.last_watched_at)}
                        </span>
                      </div>
                    </div>

                    {/* Quick remove button */}
                    <button
                      className="btn btn-icon btn-secondary"
                      style={{ width: '28px', height: '28px', color: 'var(--text-dim)' }}
                      title="Retirer cet épisode de l'historique"
                      onClick={(e) => handleDeleteItem(video.animeTitle, video.epKey, e)}
                    >
                      <X size={14} />
                    </button>
                  </div>

                  {/* Watched / Progression Status */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '4px' }}>
                    {video.watched ? (
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        color: 'var(--accent-green)',
                        background: 'rgba(46, 160, 67, 0.15)',
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-full)'
                      }}>
                        <Check size={12} /> Vu en entier
                      </span>
                    ) : (
                      <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                        Progression : <strong style={{ color: '#fff' }}>{formatTime(video.position_sec)}</strong> / {formatTime(video.duration_sec)} ({Math.round(video.progress_percent)}%)
                      </span>
                    )}
                  </div>

                  {/* Actions Row */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px', marginTop: '8px' }}>
                    <button
                      className="btn btn-primary"
                      style={{
                        padding: '6px 14px',
                        fontSize: '0.8rem',
                        background: '#FF0000',
                        borderColor: '#FF0000',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontWeight: 700
                      }}
                      disabled={isResuming}
                      aria-busy={isResuming}
                      onClick={() => play(video)}
                    >
                      {isResuming ? <Loader2 className="animate-spin" size={13} /> : <Play size={13} fill="#fff" />}
                      {video.position_sec > 10 && !video.watched ? "Reprendre" : "Revoir"}
                    </button>

                    <button
                      className="btn btn-secondary"
                      style={{ padding: '6px 12px', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '5px' }}
                      onClick={(e) => handleToggleWatched(video.animeTitle, video.season, video.epId, video.watched, e)}
                    >
                      <CheckCircle2 size={13} color={video.watched ? 'var(--accent-green)' : 'currentColor'} />
                      {video.watched ? "Marquer non vu" : "Marquer comme vu"}
                    </button>

                    <button
                      className="btn btn-secondary"
                      style={{ padding: '6px 10px', fontSize: '0.78rem' }}
                      onClick={() => openAnime(video)}
                      title="Voir la fiche complète de l'anime"
                    >
                      <ExternalLink size={13} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
