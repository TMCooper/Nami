import React, { useState, useEffect } from 'react';
import {
  HardDrive,
  Play,
  Folder,
  Loader2,
  RefreshCw,
  Trash2,
  AlertTriangle,
  CheckSquare,
  Square,
  Film,
  ArrowLeft,
  Tv,
  BookOpen,
  Bookmark
} from 'lucide-react';
import MangaReaderModal from './MangaReaderModal';

// Files on the server: only the super administrator deletes them (the server refuses the others)
export default function OfflineLibraryView({ onPlayEpisode, canDelete = false }) {
  const [library, setLibrary] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedAnimeTitle, setSelectedAnimeTitle] = useState(null);
  const [activeSeasonIdx, setActiveSeasonIdx] = useState(0);
  const [selectedEpisodes, setSelectedEpisodes] = useState({});
  const [deleteConfirm, setDeleteConfirm] = useState(null); // { type: 'anime'|'episodes', animeTitle, singlePath? }
  const [isDeleting, setIsDeleting] = useState(false);
  const [mediaTypeFilter, setMediaTypeFilter] = useState('all'); // 'all' | 'anime' | 'manga'
  const [readingChapter, setReadingChapter] = useState(null);

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

  const currentAnime = library.find(a => a.anime_title === selectedAnimeTitle) || null;
  const currentSeason = currentAnime?.seasons?.[activeSeasonIdx] || currentAnime?.seasons?.[0] || null;
  const scanSeason = currentAnime?.seasons?.find(s => s.is_scans) || null;

  const toggleEpisodeSelect = (key) => {
    setSelectedEpisodes(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  const selectAllInSeason = (seasonEpisodes) => {
    const allSelected = seasonEpisodes.every(ep => selectedEpisodes[ep.file_path]);
    const updates = {};
    seasonEpisodes.forEach(ep => {
      updates[ep.file_path] = !allSelected;
    });
    setSelectedEpisodes(prev => ({ ...prev, ...updates }));
  };

  const handleDeleteAnime = async (animeTitle) => {
    setIsDeleting(true);
    try {
      const res = await fetch(`/api/library/anime?anime_title=${encodeURIComponent(animeTitle)}`, { method: 'DELETE' });
      if (res.ok) {
        fetchLibrary();
        setDeleteConfirm(null);
        setSelectedAnimeTitle(null);
      }
    } catch (err) {
      console.error("Delete anime error:", err);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDeleteSelectedEpisodes = async () => {
    const paths = Object.entries(selectedEpisodes).filter(([, v]) => v).map(([k]) => k);
    if (paths.length === 0) return;
    setIsDeleting(true);
    try {
      for (const p of paths) {
        await fetch(`/api/library/episode?file_path=${encodeURIComponent(p)}`, { method: 'DELETE' });
      }
      setSelectedEpisodes({});
      setDeleteConfirm(null);
      fetchLibrary();
    } catch (err) {
      console.error("Delete episodes error:", err);
    } finally {
      setIsDeleting(false);
    }
  };

  const selectedCount = Object.values(selectedEpisodes).filter(Boolean).length;

  if (isLoading) {
    return (
      <div style={{ padding: '80px', textAlign: 'center', color: 'var(--text-muted)' }}>
        <Loader2 className="animate-spin" size={32} color="var(--primary)" style={{ margin: '0 auto 12px auto' }} />
        <span style={{ fontSize: '0.95rem' }}>Scan des fichiers vidéo et mangas sur le disque...</span>
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
          width: '68px',
          height: '68px',
          borderRadius: '50%',
          background: 'rgba(56, 139, 253, 0.1)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: '1px solid rgba(56, 139, 253, 0.2)'
        }}>
          <HardDrive size={32} color="#58A6FF" />
        </div>
        <h3 style={{ fontSize: '1.25rem', color: '#fff', fontWeight: 700 }}>Aucun contenu téléchargé sur le disque</h3>
        <p style={{ maxWidth: '460px', fontSize: '0.88rem', lineHeight: '1.5' }}>
          Les épisodes et chapitres de manga téléchargés sont stockés localement sur votre machine hôte (dossier <code style={{ color: '#58A6FF' }}>/downloads</code>). Vous pouvez les regarder et les lire hors-ligne à tout moment !
        </p>
      </div>
    );
  }

  // --- VIEW 2: DEDICATED SHOWCASE VIEW FOR SELECTED ANIME / MANGA ---
  if (currentAnime) {
    const totalSize = currentAnime.seasons.reduce((acc, s) => acc + s.episodes.reduce((a, e) => a + (e.size_mb || 0), 0), 0);
    const allSeasonEpisodes = currentSeason?.episodes || [];
    const isScanSeason = !!currentSeason?.is_scans;

    const formattedEpisodesForPlayer = !isScanSeason ? allSeasonEpisodes.map(e => ({
      num: e.num,
      title: `Épisode ${e.num}`,
      file_path: e.file_path,
      url: e.file_path,
      embed_url: e.file_path
    })) : [];

    // Retrieve saved reading progress for manga resume
    const savedMangaProgress = (() => {
      try {
        const raw = localStorage.getItem(`nami_manga_progress_${currentAnime.anime_title}`);
        return raw ? JSON.parse(raw) : null;
      } catch (e) {
        return null;
      }
    })();

    const lastReadChapterNum = savedMangaProgress?.chapter || scanSeason?.episodes?.[0]?.num || 1;
    const lastReadPageDisplay = savedMangaProgress?.pageIndex != null ? savedMangaProgress.pageIndex + 1 : null;

    return (
      <div style={{ padding: '20px 0', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {/* Back navigation button */}
        <div>
          <button
            className="btn btn-secondary"
            onClick={() => { setSelectedAnimeTitle(null); setSelectedEpisodes({}); }}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', fontSize: '0.86rem', padding: '7px 14px' }}
          >
            <ArrowLeft size={16} /> Retour à la Médiathèque
          </button>
        </div>

        {/* Hero Showcase Card */}
        <div
          className="surface-card animate-fade-in"
          style={{
            borderRadius: 'var(--radius-md)',
            padding: '24px',
            display: 'flex',
            gap: '24px',
            alignItems: 'center',
            background: 'linear-gradient(135deg, rgba(15, 15, 15, 0.95), rgba(15, 15, 15, 0.98))',
            border: '1px solid var(--border-color)',
            flexWrap: 'wrap'
          }}
        >
          {/* Cover Poster */}
          <div style={{
            width: '130px',
            height: '185px',
            borderRadius: 'var(--radius-sm)',
            overflow: 'hidden',
            boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
            flexShrink: 0,
            background: '#0F0F0F'
          }}>
            {currentAnime.cover ? (
              <img
                src={currentAnime.cover}
                alt={currentAnime.anime_title}
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                  if (e.currentTarget.nextSibling) e.currentTarget.nextSibling.style.display = 'flex';
                }}
              />
            ) : null}
            <div
              style={{
                width: '100%',
                height: '100%',
                display: currentAnime.cover ? 'none' : 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: `linear-gradient(135deg, hsl(${(currentAnime.anime_title.charCodeAt(0) * 37) % 360}, 60%, 25%), hsl(${(currentAnime.anime_title.charCodeAt(0) * 37 + 60) % 360}, 50%, 15%))`
              }}
            >
              <Film size={36} color="rgba(255,255,255,0.4)" />
            </div>
          </div>

          {/* Details & Actions */}
          <div style={{ flex: 1, minWidth: '240px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              <span className="badge" style={{ background: 'rgba(63, 185, 80, 0.2)', color: '#3FB950', border: '1px solid rgba(63, 185, 80, 0.3)' }}>
                💾 Stocké en local
              </span>
              {currentAnime.total_episodes > 0 && (
                <span className="badge" style={{ background: 'rgba(56, 139, 253, 0.15)', color: '#58A6FF' }}>
                  🎬 {currentAnime.total_episodes} épisode(s)
                </span>
              )}
              {currentAnime.total_chapters > 0 && (
                <span className="badge" style={{ background: 'rgba(163, 113, 247, 0.2)', color: '#d2a8ff', border: '1px solid rgba(163, 113, 247, 0.3)' }}>
                  📖 {currentAnime.total_chapters} chapitre(s)
                </span>
              )}
              <span className="badge" style={{
                background: 'rgba(15, 15, 15, 0.88)',
                color: '#ffffff',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                fontWeight: 600,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px'
              }}>
                💾 {Math.round(totalSize)} Mo
              </span>
            </div>

            <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: '#fff', margin: 0, lineHeight: 1.2 }}>
              {currentAnime.anime_title}
            </h1>

            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', margin: 0 }}>
              Contenu hors-ligne prêt à la lecture et au visionnage sans dépendance réseau.
            </p>

            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '6px', flexWrap: 'wrap' }}>
              {/* Watch Video Button */}
              {formattedEpisodesForPlayer.length > 0 && (
                <button
                  className="btn btn-primary"
                  onClick={() => onPlayEpisode(
                    currentAnime.anime_title,
                    currentSeason?.season_name || "Saison 1",
                    formattedEpisodesForPlayer[0],
                    formattedEpisodesForPlayer,
                    currentAnime.cover || '',
                    0,
                    formattedEpisodesForPlayer[0].file_path
                  )}
                  style={{ padding: '8px 18px', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '8px' }}
                >
                  <Play size={16} fill="#fff" /> Tout regarder (Ép. 1)
                </button>
              )}

              {/* Read Manga Resume Button */}
              {scanSeason && scanSeason.episodes?.length > 0 && (
                <button
                  className="btn btn-primary"
                  style={{
                    background: 'linear-gradient(135deg, #8957e5, #6e40c9)',
                    borderColor: '#8957e5',
                    padding: '8px 18px',
                    fontSize: '0.9rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}
                  onClick={() => {
                    const scanIdx = currentAnime.seasons.findIndex(s => s.is_scans);
                    if (scanIdx !== -1) setActiveSeasonIdx(scanIdx);
                    const targetChap = scanSeason.episodes.find(c => c.num === lastReadChapterNum) || scanSeason.episodes[0];
                    setReadingChapter(targetChap);
                  }}
                >
                  <BookOpen size={16} fill="#fff" />
                  {savedMangaProgress
                    ? `Reprendre Manga (Chap. ${lastReadChapterNum}${lastReadPageDisplay ? `, p. ${lastReadPageDisplay}` : ''})`
                    : `Lire le Manga (Chap. ${lastReadChapterNum})`}
                </button>
              )}

              {canDelete && (<button
                className="btn btn-secondary"
                onClick={() => setDeleteConfirm({ type: 'anime', animeTitle: currentAnime.anime_title })}
                style={{ padding: '8px 16px', fontSize: '0.85rem', color: '#f85149', borderColor: 'rgba(248, 81, 73, 0.3)' }}
              >
                <Trash2 size={15} /> Supprimer du disque
              </button>)}
            </div>
          </div>
        </div>

        {/* Season & Scans Selector Tabs */}
        {currentAnime.seasons.length > 1 && (
          <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px', flexWrap: 'wrap' }}>
            {currentAnime.seasons.map((s, sIdx) => {
              const isScan = !!s.is_scans;
              const isActive = activeSeasonIdx === sIdx;
              return (
                <button
                  key={sIdx}
                  className={`btn ${isActive ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => { setActiveSeasonIdx(sIdx); setSelectedEpisodes({}); }}
                  style={{
                    fontSize: '0.84rem',
                    padding: '6px 14px',
                    background: isActive && isScan ? 'linear-gradient(135deg, #8957e5, #6e40c9)' : undefined,
                    borderColor: isScan ? 'rgba(163, 113, 247, 0.4)' : undefined
                  }}
                >
                  {isScan ? (
                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <BookOpen size={14} color="#d2a8ff" /> Scans & Mangas ({s.episodes.length} chap.)
                    </span>
                  ) : (
                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Folder size={14} /> {s.season_name} ({s.episodes.length} ép.)
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Section Header & Multi-select Toolbar */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {isScanSeason ? (
              <BookOpen size={18} color="#d2a8ff" />
            ) : (
              <Tv size={18} color="var(--accent-cyan)" />
            )}
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#fff', margin: 0 }}>
              {isScanSeason ? "Chapitres de Scan téléchargés" : (currentSeason?.season_name || "Épisodes")}
            </h3>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              ({allSeasonEpisodes.length} {isScanSeason ? `chapitre${allSeasonEpisodes.length > 1 ? 's' : ''}` : `vidéo${allSeasonEpisodes.length > 1 ? 's' : ''}`})
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {canDelete && selectedCount > 0 && (
              <button
                className="btn btn-primary"
                style={{ fontSize: '0.8rem', padding: '5px 12px', background: '#f85149', borderColor: '#f85149' }}
                onClick={() => setDeleteConfirm({ type: 'episodes' })}
              >
                <Trash2 size={13} /> Supprimer ({selectedCount})
              </button>
            )}

            <button
              className="btn btn-secondary"
              style={{ fontSize: '0.8rem', padding: '5px 12px' }}
              onClick={() => selectAllInSeason(allSeasonEpisodes)}
            >
              {allSeasonEpisodes.length > 0 && allSeasonEpisodes.every(ep => selectedEpisodes[ep.file_path]) ? (
                <><CheckSquare size={13} /> Tout désélectionner</>
              ) : (
                <><Square size={13} /> Tout sélectionner</>
              )}
            </button>
          </div>
        </div>

        {/* --- CONTENT GRID: SCANS VS VIDEOS --- */}
        {isScanSeason ? (
          /* MANGA CHAPTERS GRID */
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
            gap: '16px'
          }}>
            {allSeasonEpisodes.map((chap, cIdx) => {
              const isSelected = !!selectedEpisodes[chap.file_path];
              const firstPageUrl = chap.pages && chap.pages.length > 0
                ? `/api/stream/local?file_path=${encodeURIComponent(chap.pages[0])}`
                : currentAnime.cover;

              return (
                <div
                  key={cIdx}
                  className="surface-card animate-fade-in"
                  style={{
                    borderRadius: 'var(--radius-sm)',
                    overflow: 'hidden',
                    background: isSelected ? 'rgba(248, 81, 73, 0.08)' : '#0F0F0F',
                    border: isSelected ? '1px solid rgba(248, 81, 73, 0.5)' : '1px solid var(--border-color)',
                    display: 'flex',
                    flexDirection: 'column',
                    transition: 'transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease',
                    position: 'relative'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-3px)';
                    e.currentTarget.style.boxShadow = '0 6px 20px rgba(0,0,0,0.5)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'translateY(0)';
                    e.currentTarget.style.boxShadow = 'none';
                  }}
                >
                  {/* Thumbnail / First page preview */}
                  <div
                    style={{
                      position: 'relative',
                      width: '100%',
                      aspectRatio: '3 / 4',
                      background: '#181818',
                      overflow: 'hidden',
                      cursor: 'pointer'
                    }}
                    onClick={() => setReadingChapter(chap)}
                  >
                    <img
                      src={firstPageUrl}
                      alt={`Chapitre ${chap.num}`}
                      style={{
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover',
                        display: 'block',
                        transition: 'transform 0.3s ease'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.04)'}
                      onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                        if (e.currentTarget.nextSibling) e.currentTarget.nextSibling.style.display = 'flex';
                      }}
                    />

                    {/* Fallback plate */}
                    <div style={{
                      width: '100%',
                      height: '100%',
                      display: 'none',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: 'linear-gradient(135deg, #181818, #0F0F0F)',
                      flexDirection: 'column',
                      gap: '8px'
                    }}>
                      <BookOpen size={28} color="rgba(255,255,255,0.3)" />
                      <span style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)' }}>Chapitre {chap.num}</span>
                    </div>

                    {/* Hover Read Overlay */}
                    <div
                      style={{
                        position: 'absolute',
                        inset: 0,
                        background: 'rgba(0,0,0,0.4)',
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
                        padding: '8px 16px',
                        borderRadius: '20px',
                        background: 'linear-gradient(135deg, #8957e5, #6e40c9)',
                        color: '#fff',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontWeight: 700,
                        fontSize: '0.82rem',
                        boxShadow: '0 4px 14px rgba(137, 87, 229, 0.6)'
                      }}>
                        <BookOpen size={15} /> Lire le Scan
                      </div>
                    </div>

                    {/* Pages count badge */}
                    <div style={{
                      position: 'absolute',
                      bottom: '6px',
                      right: '6px',
                      background: 'rgba(0, 0, 0, 0.85)',
                      color: '#fff',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      fontSize: '0.72rem',
                      fontWeight: 700
                    }}>
                      {chap.pages_count} pages • {chap.size_mb} Mo
                    </div>

                    {/* Selection Checkbox */}
                    <div
                      onClick={(e) => { e.stopPropagation(); toggleEpisodeSelect(chap.file_path); }}
                      style={{
                        position: 'absolute',
                        top: '6px',
                        left: '6px',
                        background: isSelected ? 'rgba(248, 81, 73, 0.9)' : 'rgba(0,0,0,0.6)',
                        borderRadius: '4px',
                        padding: '4px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        cursor: 'pointer'
                      }}
                      title="Sélectionner pour suppression"
                    >
                      {isSelected ? <CheckSquare size={14} color="#fff" /> : <Square size={14} color="#fff" />}
                    </div>
                  </div>

                  {/* Card Info below */}
                  <div style={{ padding: '10px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                    <div style={{ cursor: 'pointer', flex: 1, minWidth: 0 }} onClick={() => setReadingChapter(chap)}>
                      <span style={{ fontSize: '0.88rem', fontWeight: 700, color: '#fff', display: 'block' }}>
                        {chap.title || `Chapitre ${chap.num}`}
                      </span>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                        {chap.pages_count} pages sauvegardées
                      </span>
                    </div>

                    {canDelete && (<button
                      className="btn btn-icon btn-secondary"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteConfirm({
                          type: 'episodes',
                          animeTitle: currentAnime.anime_title,
                          singlePath: chap.file_path
                        });
                      }}
                      style={{ width: '28px', height: '28px', color: 'var(--text-muted)' }}
                      title="Supprimer ce chapitre"
                    >
                      <Trash2 size={13} />
                    </button>)}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          /* YOUTUBE-STYLE 16:9 VIDEO CARDS */
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: '16px'
          }}>
            {allSeasonEpisodes.map((ep, epIdx) => {
              const isSelected = !!selectedEpisodes[ep.file_path];
              const epDataForPlayer = {
                num: ep.num,
                title: `Épisode ${ep.num}`,
                file_path: ep.file_path,
                url: ep.file_path,
                embed_url: ep.file_path
              };

              return (
                <div
                  key={epIdx}
                  className="surface-card animate-fade-in"
                  style={{
                    borderRadius: 'var(--radius-sm)',
                    overflow: 'hidden',
                    background: isSelected ? 'rgba(248, 81, 73, 0.08)' : '#0F0F0F',
                    border: isSelected ? '1px solid rgba(248, 81, 73, 0.5)' : '1px solid var(--border-color)',
                    display: 'flex',
                    flexDirection: 'column',
                    transition: 'transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease',
                    position: 'relative'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-3px)';
                    e.currentTarget.style.boxShadow = '0 6px 20px rgba(0,0,0,0.5)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'translateY(0)';
                    e.currentTarget.style.boxShadow = 'none';
                  }}
                >
                  {/* 16:9 Thumbnail Box */}
                  <div
                    style={{
                      position: 'relative',
                      width: '100%',
                      aspectRatio: '16 / 9',
                      background: '#181818',
                      overflow: 'hidden',
                      cursor: 'pointer'
                    }}
                    onClick={() => onPlayEpisode(
                      currentAnime.anime_title,
                      currentSeason?.season_name || "Saison 1",
                      epDataForPlayer,
                      formattedEpisodesForPlayer,
                      currentAnime.cover || '',
                      0,
                      ep.file_path
                    )}
                  >
                    <img
                      src={ep.thumbnail || `/api/stream/thumbnail?file_path=${encodeURIComponent(ep.file_path)}`}
                      alt={`Épisode ${ep.num}`}
                      style={{
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover',
                        display: 'block',
                        transition: 'transform 0.3s ease'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.04)'}
                      onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                        if (e.currentTarget.nextSibling) e.currentTarget.nextSibling.style.display = 'flex';
                      }}
                    />

                    <div style={{
                      width: '100%',
                      height: '100%',
                      display: 'none',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: 'linear-gradient(135deg, #181818, #0F0F0F)'
                    }}>
                      <Film size={28} color="rgba(255,255,255,0.2)" />
                    </div>

                    {/* Play Button Overlay */}
                    <div
                      style={{
                        position: 'absolute',
                        inset: 0,
                        background: 'rgba(0,0,0,0.3)',
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
                        width: '48px',
                        height: '48px',
                        borderRadius: '50%',
                        background: '#ff0000',
                        boxShadow: '0 0 16px rgba(255,0,0,0.6)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#fff',
                        transform: 'scale(0.95)',
                        transition: 'transform 0.15s ease'
                      }}>
                        <Play size={20} fill="#fff" style={{ marginLeft: '3px' }} />
                      </div>
                    </div>

                    <div style={{
                      position: 'absolute',
                      bottom: '6px',
                      right: '6px',
                      background: 'rgba(0, 0, 0, 0.85)',
                      color: '#fff',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      fontSize: '0.72rem',
                      fontWeight: 700
                    }}>
                      {ep.size_mb} Mo
                    </div>

                    <div
                      onClick={(e) => { e.stopPropagation(); toggleEpisodeSelect(ep.file_path); }}
                      style={{
                        position: 'absolute',
                        top: '6px',
                        left: '6px',
                        background: isSelected ? 'rgba(248, 81, 73, 0.9)' : 'rgba(0,0,0,0.6)',
                        borderRadius: '4px',
                        padding: '4px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        cursor: 'pointer'
                      }}
                      title="Sélectionner"
                    >
                      {isSelected ? <CheckSquare size={14} color="#fff" /> : <Square size={14} color="#fff" />}
                    </div>
                  </div>

                  <div style={{ padding: '10px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                    <div
                      style={{ cursor: 'pointer', flex: 1, minWidth: 0 }}
                      onClick={() => onPlayEpisode(
                        currentAnime.anime_title,
                        currentSeason?.season_name || "Saison 1",
                        epDataForPlayer,
                        formattedEpisodesForPlayer,
                        currentAnime.cover || '',
                        0,
                        ep.file_path
                      )}
                    >
                      <span style={{ fontSize: '0.88rem', fontWeight: 700, color: '#fff', display: 'block' }}>
                        Épisode {ep.num}
                      </span>
                      <span style={{
                        fontSize: '0.72rem',
                        color: 'var(--text-muted)',
                        display: 'block',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
                      }}>
                        {ep.filename}
                      </span>
                    </div>

                    {canDelete && (<button
                      className="btn btn-icon btn-secondary"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteConfirm({
                          type: 'episodes',
                          animeTitle: currentAnime.anime_title,
                          singlePath: ep.file_path
                        });
                      }}
                      style={{ width: '28px', height: '28px', color: 'var(--text-muted)' }}
                      title="Supprimer cet épisode"
                    >
                      <Trash2 size={13} />
                    </button>)}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Delete Confirmation Modal */}
        {deleteConfirm && (
          <div
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0,0,0,0.8)',
              zIndex: 9999,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '20px'
            }}
            onClick={() => setDeleteConfirm(null)}
          >
            <div
              className="surface animate-fade-in"
              style={{
                background: 'var(--bg-surface)',
                borderRadius: 'var(--radius-md)',
                padding: '24px',
                maxWidth: '440px',
                width: '100%',
                display: 'flex',
                flexDirection: 'column',
                gap: '16px',
                border: '1px solid var(--border-color)'
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#f85149' }}>
                <AlertTriangle size={24} />
                <h3 style={{ fontSize: '1.15rem', fontWeight: 800, margin: 0, color: '#fff' }}>
                  Confirmation de suppression
                </h3>
              </div>

              <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)', lineHeight: '1.5', margin: 0 }}>
                {deleteConfirm.type === 'anime' ? (
                  <>Êtes-vous sûr de vouloir supprimer tous les médias de <strong>{deleteConfirm.animeTitle}</strong> du disque ? Vos statistiques et votre historique seront conservés.</>
                ) : deleteConfirm.singlePath ? (
                  <>Êtes-vous sûr de vouloir supprimer cet élément du disque ?</>
                ) : (
                  <>Êtes-vous sûr de vouloir supprimer les <strong>{selectedCount}</strong> éléments sélectionnés ?</>
                )}
              </p>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button className="btn btn-secondary" onClick={() => setDeleteConfirm(null)}>
                  Annuler
                </button>
                <button
                  className="btn btn-primary"
                  style={{ background: '#f85149', borderColor: '#f85149' }}
                  disabled={isDeleting}
                  onClick={() => {
                    if (deleteConfirm.type === 'anime') {
                      handleDeleteAnime(deleteConfirm.animeTitle);
                    } else if (deleteConfirm.singlePath) {
                      setIsDeleting(true);
                      fetch(`/api/library/episode?file_path=${encodeURIComponent(deleteConfirm.singlePath)}`, { method: 'DELETE' })
                        .then(() => {
                          setDeleteConfirm(null);
                          fetchLibrary();
                        })
                        .finally(() => setIsDeleting(false));
                    } else {
                      handleDeleteSelectedEpisodes();
                    }
                  }}
                >
                  {isDeleting ? 'Suppression...' : 'Supprimer définitivement'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Offline Manga Reader Modal */}
        {readingChapter && scanSeason && (
          <MangaReaderModal
            mangaTitle={currentAnime.anime_title}
            initialChapterNum={readingChapter.num}
            chapters={scanSeason.episodes}
            onClose={() => setReadingChapter(null)}
          />
        )}
      </div>
    );
  }

  // --- VIEW 1: MAIN GALLERY OF DOWNLOADED ANIMES & MANGAS ---
  const animesCount = library.filter(a => a.has_videos).length;
  const mangasCount = library.filter(a => a.has_scans).length;

  const filteredLibrary = library.filter(item => {
    if (mediaTypeFilter === 'anime') return item.has_videos;
    if (mediaTypeFilter === 'manga') return item.has_scans;
    return true;
  });

  return (
    <div style={{ padding: '24px 0', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Top Header & Filter Controls */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: '40px',
            height: '40px',
            borderRadius: '10px',
            background: 'rgba(63, 185, 80, 0.15)',
            border: '1px solid rgba(63, 185, 80, 0.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <HardDrive size={22} color="#3FB950" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h2 style={{ fontSize: '1.35rem', fontWeight: 800, margin: 0, color: '#fff' }}>Médiathèque Locale</h2>
              <span className="badge" style={{ background: 'rgba(46, 160, 67, 0.2)', color: '#3FB950', border: '1px solid rgba(46, 160, 67, 0.3)' }}>
                {library.length} série(s)
              </span>
            </div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', margin: '2px 0 0 0' }}>
              Vos animes et mangas téléchargés stockés localement sur le disque
            </p>
          </div>
        </div>

        {/* Filter Pills & Re-scan Button */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <div style={{
            display: 'flex',
            background: 'var(--bg-surface)',
            padding: '3px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-color)',
            gap: '2px'
          }}>
            <button
              className={`btn ${mediaTypeFilter === 'all' ? 'btn-primary' : 'btn-ghost'}`}
              style={{ fontSize: '0.82rem', padding: '5px 12px' }}
              onClick={() => setMediaTypeFilter('all')}
            >
              Tout ({library.length})
            </button>
            <button
              className={`btn ${mediaTypeFilter === 'anime' ? 'btn-primary' : 'btn-ghost'}`}
              style={{ fontSize: '0.82rem', padding: '5px 12px', display: 'flex', alignItems: 'center', gap: '5px' }}
              onClick={() => setMediaTypeFilter('anime')}
            >
              <Tv size={13} /> Animes ({animesCount})
            </button>
            <button
              className={`btn ${mediaTypeFilter === 'manga' ? 'btn-primary' : 'btn-ghost'}`}
              style={{ fontSize: '0.82rem', padding: '5px 12px', display: 'flex', alignItems: 'center', gap: '5px' }}
              onClick={() => setMediaTypeFilter('manga')}
            >
              <BookOpen size={13} /> Mangas ({mangasCount})
            </button>
          </div>

          <button className="btn btn-secondary" style={{ fontSize: '0.82rem', padding: '6px 12px' }} onClick={fetchLibrary} title="Re-scanner les répertoires">
            <RefreshCw size={13} /> Re-scanner
          </button>
        </div>
      </div>

      {filteredLibrary.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-muted)' }}>
          <BookOpen size={36} color="var(--border-color)" style={{ margin: '0 auto 12px auto' }} />
          <p style={{ fontSize: '0.95rem', margin: 0 }}>Aucun média correspondant au filtre sélectionné.</p>
        </div>
      ) : (
        /* Grid of anime & manga cards with real posters */
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
          gap: '16px'
        }}>
          {filteredLibrary.map((anime, idx) => {
            const totalSize = anime.seasons.reduce((acc, s) => acc + s.episodes.reduce((a, e) => a + (e.size_mb || 0), 0), 0);
            const hasVideos = !!anime.has_videos;
            const hasScans = !!anime.has_scans;

            return (
              <div
                key={idx}
                className="surface-card animate-fade-in"
                style={{
                  borderRadius: 'var(--radius-sm)',
                  overflow: 'hidden',
                  cursor: 'pointer',
                  position: 'relative',
                  transition: 'transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease',
                  display: 'flex',
                  flexDirection: 'column',
                  border: '1px solid var(--border-color)',
                  background: '#181818'
                }}
                onClick={() => {
                  setSelectedAnimeTitle(anime.anime_title);
                  // Default to first season, or scans if only scans exist
                  const firstSeasonIdx = anime.seasons.findIndex(s => !s.is_scans);
                  setActiveSeasonIdx(firstSeasonIdx !== -1 ? firstSeasonIdx : 0);
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-4px)';
                  e.currentTarget.style.borderColor = hasScans && !hasVideos ? '#8957e5' : 'var(--accent-cyan)';
                  e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.6)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.borderColor = 'var(--border-color)';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              >
                {/* Card Cover with Badges */}
                <div style={{ position: 'relative', width: '100%', height: '260px', overflow: 'hidden', background: '#0F0F0F' }}>
                  {anime.cover ? (
                    <img
                      src={anime.cover}
                      alt={anime.anime_title}
                      style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                        if (e.currentTarget.nextSibling) e.currentTarget.nextSibling.style.display = 'flex';
                      }}
                    />
                  ) : null}

                  {/* Graceful gradient fallback */}
                  <div style={{
                    width: '100%',
                    height: '100%',
                    background: `linear-gradient(135deg, hsl(${(anime.anime_title.charCodeAt(0) * 37) % 360}, 60%, 25%), hsl(${(anime.anime_title.charCodeAt(0) * 37 + 60) % 360}, 50%, 15%))`,
                    display: anime.cover ? 'none' : 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexDirection: 'column',
                    gap: '8px'
                  }}>
                    {hasScans && !hasVideos ? (
                      <BookOpen size={36} color="rgba(255,255,255,0.4)" />
                    ) : (
                      <Film size={36} color="rgba(255,255,255,0.3)" />
                    )}
                    <span style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', fontWeight: 600 }}>
                      {hasScans && `${anime.total_chapters} chap.`} {hasVideos && `${anime.total_episodes} ép.`}
                    </span>
                  </div>

                  {/* Disk Size Badge */}
                  <div style={{ position: 'absolute', top: '8px', left: '8px', zIndex: 5 }}>
                    <span className="badge" style={{
                      background: 'rgba(15, 15, 15, 0.88)',
                      color: '#ffffff',
                      border: '1px solid rgba(255, 255, 255, 0.2)',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      backdropFilter: 'blur(8px)',
                      boxShadow: '0 2px 8px rgba(0, 0, 0, 0.5)',
                      padding: '3px 8px',
                      borderRadius: 'var(--radius-full)',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px'
                    }}>
                      <span>💾</span>
                      <span>{Math.round(totalSize)} Mo</span>
                    </span>
                  </div>

                  {/* Media Count Badges (top-right) */}
                  <div style={{ position: 'absolute', top: '8px', right: '8px', zIndex: 5, display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-end' }}>
                    {hasVideos && (
                      <span className="badge" style={{ background: 'rgba(0, 0, 0, 0.7)', color: '#fff', fontSize: '0.68rem', backdropFilter: 'blur(4px)' }}>
                        🎬 {anime.total_episodes} ép.
                      </span>
                    )}
                    {hasScans && (
                      <span className="badge" style={{ background: 'rgba(137, 87, 229, 0.75)', color: '#fff', fontSize: '0.68rem', backdropFilter: 'blur(4px)' }}>
                        📖 {anime.total_chapters} chap.
                      </span>
                    )}
                  </div>

                  {/* Hover Overlay */}
                  <div
                    style={{
                      position: 'absolute',
                      inset: 0,
                      background: 'linear-gradient(to top, rgba(15, 15, 15, 0.85) 0%, transparent 60%)',
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
                      width: '44px',
                      height: '44px',
                      borderRadius: '50%',
                      background: hasScans && !hasVideos ? '#8957e5' : '#3FB950',
                      color: '#fff',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      boxShadow: hasScans && !hasVideos ? '0 0 16px rgba(137, 87, 229, 0.6)' : '0 0 16px rgba(63, 185, 80, 0.6)'
                    }}>
                      {hasScans && !hasVideos ? (
                        <BookOpen size={18} fill="#fff" />
                      ) : (
                        <Play size={18} fill="#fff" style={{ marginLeft: '2px' }} />
                      )}
                    </div>
                  </div>
                </div>

                {/* Card Title */}
                <div style={{ padding: '10px 12px' }}>
                  <h3 style={{
                    fontSize: '0.9rem',
                    fontWeight: 700,
                    color: '#fff',
                    margin: 0,
                    lineHeight: '1.3',
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden'
                  }}>
                    {anime.anime_title}
                  </h3>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
