import React, { useState, useEffect, useRef } from 'react';
import { DEFAULT_PAGE_IMAGE } from '../utils/placeholders';
import { 
  X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Maximize, 
  Minimize, BookOpen, Layers, Check, Loader2, Bookmark 
} from 'lucide-react';

export default function MangaReaderModal({
  mangaTitle,
  initialChapterNum,
  chapters = [], // [{ num, title, pages, pages_count }]
  onClose
}) {
  const progressKey = `nami_manga_progress_${mangaTitle}`;

  // Read saved reading progress from localStorage
  const getSavedProgress = () => {
    try {
      const raw = localStorage.getItem(progressKey);
      if (raw) return JSON.parse(raw);
    } catch (e) {}
    return null;
  };

  const savedProgress = getSavedProgress();
  const startChapter = (initialChapterNum != null) 
    ? initialChapterNum 
    : (savedProgress?.chapter || chapters[0]?.num || 1);
  const startPage = (savedProgress && savedProgress.chapter === startChapter) 
    ? (savedProgress.pageIndex || 0) 
    : 0;

  const [currentChapterNum, setCurrentChapterNum] = useState(startChapter);
  const [currentPageIndex, setCurrentPageIndex] = useState(startPage);
  const [readingMode, setReadingMode] = useState('webtoon'); // Default to Webtoon mode
  const [zoomLevel, setZoomLevel] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isImageLoading, setIsImageLoading] = useState(true);

  const containerRef = useRef(null);

  // Find active chapter object
  const currentChapter = chapters.find(c => c.num === currentChapterNum) || chapters[0] || { pages: [] };
  const pages = currentChapter.pages || [];
  const totalPages = pages.length;

  const saveProgress = (chapNum, pageIdx) => {
    try {
      localStorage.setItem(progressKey, JSON.stringify({
        mangaTitle,
        chapter: chapNum,
        pageIndex: pageIdx,
        updatedAt: Date.now()
      }));
    } catch (e) {}
  };

  // Reset page when chapter changes, or resume if matching saved
  useEffect(() => {
    const saved = getSavedProgress();
    const targetP = (saved && saved.chapter === currentChapterNum) ? (saved.pageIndex || 0) : 0;
    setCurrentPageIndex(targetP);
    setIsImageLoading(true);
    saveProgress(currentChapterNum, targetP);
  }, [currentChapterNum]);

  // Track scroll position in Webtoon mode via IntersectionObserver
  useEffect(() => {
    if (readingMode !== 'webtoon' || totalPages === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const idx = Number(entry.target.getAttribute('data-page-index'));
            if (!isNaN(idx)) {
              setCurrentPageIndex(idx);
              saveProgress(currentChapterNum, idx);
            }
          }
        });
      },
      {
        root: null,
        rootMargin: '-20% 0px -40% 0px',
        threshold: 0.1
      }
    );

    const items = document.querySelectorAll('.webtoon-page-item');
    items.forEach(el => observer.observe(el));

    return () => observer.disconnect();
  }, [currentChapterNum, readingMode, pages]);

  // Scroll to resumed page in Webtoon mode on mount or chapter resume
  useEffect(() => {
    if (readingMode === 'webtoon' && startPage > 0) {
      const scroll = () => {
        const el = document.getElementById(`webtoon-page-${startPage}`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      };
      const t1 = setTimeout(scroll, 250);
      const t2 = setTimeout(scroll, 700);
      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
      };
    }
  }, [readingMode, currentChapterNum]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'ArrowRight' || e.key === ' ') {
        handleNextPage();
      } else if (e.key === 'ArrowLeft') {
        handlePrevPage();
      } else if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentPageIndex, totalPages, currentChapterNum]);

  const handleNextPage = () => {
    if (currentPageIndex < totalPages - 1) {
      const nextIdx = currentPageIndex + 1;
      setCurrentPageIndex(nextIdx);
      setIsImageLoading(true);
      saveProgress(currentChapterNum, nextIdx);
      if (readingMode === 'webtoon') {
        document.getElementById(`webtoon-page-${nextIdx}`)?.scrollIntoView({ behavior: 'smooth' });
      }
    } else {
      // Jump to next chapter
      const currentIdx = chapters.findIndex(c => c.num === currentChapterNum);
      if (currentIdx < chapters.length - 1) {
        const nextChap = chapters[currentIdx + 1];
        setCurrentChapterNum(nextChap.num);
      }
    }
  };

  const handlePrevPage = () => {
    if (currentPageIndex > 0) {
      const prevIdx = currentPageIndex - 1;
      setCurrentPageIndex(prevIdx);
      setIsImageLoading(true);
      saveProgress(currentChapterNum, prevIdx);
      if (readingMode === 'webtoon') {
        document.getElementById(`webtoon-page-${prevIdx}`)?.scrollIntoView({ behavior: 'smooth' });
      }
    } else {
      // Jump to previous chapter last page
      const currentIdx = chapters.findIndex(c => c.num === currentChapterNum);
      if (currentIdx > 0) {
        const prevChap = chapters[currentIdx - 1];
        setCurrentChapterNum(prevChap.num);
      }
    }
  };

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen?.();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen?.();
      setIsFullscreen(false);
    }
  };

  const formatImageUrl = (url) => {
    if (!url) return '';
    if (url.startsWith('http')) {
      return `/api/img?url=${encodeURIComponent(url)}`;
    }
    return `/api/stream/local?file_path=${encodeURIComponent(url)}`;
  };

  return (
    <div 
      ref={containerRef}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 100,
        backgroundColor: '#0a0c10',
        color: '#f0f6fc',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden'
      }}
    >
      {/* Top Navigation & Controls Bar */}
      <div style={{
        height: '60px',
        padding: '0 20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'rgba(13, 17, 23, 0.95)',
        borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
        backdropFilter: 'blur(10px)',
        zIndex: 10
      }}>
        {/* Title & Chapter Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, whiteSpace: 'nowrap' }}>
            📖 {mangaTitle}
          </h2>

          <select
            value={currentChapterNum}
            onChange={(e) => {
              const num = Number(e.target.value);
              setCurrentChapterNum(num);
            }}
            style={{
              background: '#21262d',
              color: '#fff',
              border: '1px solid #30363d',
              padding: '6px 12px',
              borderRadius: '6px',
              fontSize: '0.85rem',
              cursor: 'pointer',
              fontWeight: 600
            }}
          >
            {chapters.map((ch) => (
              <option key={ch.num} value={ch.num}>
                {ch.title || `Chapitre ${ch.num}`} ({ch.pages_count} pages)
              </option>
            ))}
          </select>

          {/* Current Page Indicator Badge */}
          {totalPages > 0 && (
            <span style={{ fontSize: '0.85rem', color: '#8b949e', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Bookmark size={13} color="#58a6ff" />
              Page <strong style={{ color: '#58a6ff' }}>{currentPageIndex + 1}</strong> / {totalPages}
            </span>
          )}
        </div>

        {/* Middle: Page navigation buttons for single page mode */}
        {readingMode === 'single' && totalPages > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              className="btn btn-secondary"
              onClick={handlePrevPage}
              disabled={currentPageIndex === 0 && chapters.findIndex(c => c.num === currentChapterNum) === 0}
              style={{ padding: '6px 10px', fontSize: '0.8rem' }}
              title="Page précédente (Flèche Gauche)"
            >
              <ChevronLeft size={16} /> Précédent
            </button>

            <span style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-muted)' }}>
              Page <strong style={{ color: '#58a6ff' }}>{currentPageIndex + 1}</strong> / {totalPages}
            </span>

            <button
              className="btn btn-primary"
              onClick={handleNextPage}
              style={{ padding: '6px 12px', fontSize: '0.8rem' }}
              title="Page suivante (Flèche Droite ou Espace)"
            >
              Suivant <ChevronRight size={16} />
            </button>
          </div>
        )}

        {/* Right Controls: Mode, Zoom, Fullscreen, Close */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Mode Toggle */}
          <button
            className={`btn ${readingMode === 'webtoon' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setReadingMode('webtoon')}
            style={{ padding: '6px 10px', fontSize: '0.78rem' }}
            title="Mode Défilement Continu (Webtoon - Par Défaut)"
          >
            <Layers size={14} style={{ marginRight: '4px' }} /> Webtoon
          </button>
          <button
            className={`btn ${readingMode === 'single' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setReadingMode('single')}
            style={{ padding: '6px 10px', fontSize: '0.78rem' }}
            title="Mode Page par Page"
          >
            <BookOpen size={14} style={{ marginRight: '4px' }} /> Page
          </button>

          {/* Zoom Controls */}
          {readingMode === 'single' && (
            <div style={{ display: 'flex', gap: '4px', marginLeft: '6px' }}>
              <button
                className="btn btn-icon btn-secondary"
                style={{ width: '32px', height: '32px' }}
                onClick={() => setZoomLevel(prev => Math.max(0.7, prev - 0.15))}
                title="Dézoomer"
              >
                <ZoomOut size={15} />
              </button>
              <button
                className="btn btn-icon btn-secondary"
                style={{ width: '32px', height: '32px' }}
                onClick={() => setZoomLevel(1)}
                title="Taille normale (100%)"
              >
                100%
              </button>
              <button
                className="btn btn-icon btn-secondary"
                style={{ width: '32px', height: '32px' }}
                onClick={() => setZoomLevel(prev => Math.min(2.0, prev + 0.15))}
                title="Zoomer"
              >
                <ZoomIn size={15} />
              </button>
            </div>
          )}

          <button
            className="btn btn-icon btn-secondary"
            style={{ width: '34px', height: '34px', marginLeft: '4px' }}
            onClick={toggleFullscreen}
            title={isFullscreen ? "Quitter le plein écran" : "Plein écran"}
          >
            {isFullscreen ? <Minimize size={16} /> : <Maximize size={16} />}
          </button>

          <button
            className="btn btn-icon btn-secondary"
            style={{ width: '34px', height: '34px' }}
            onClick={onClose}
            title="Fermer le lecteur"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Reader Body */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        overflowX: 'auto',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: readingMode === 'single' ? 'center' : 'flex-start',
        padding: readingMode === 'single' ? '12px' : '24px 0',
        backgroundColor: '#07090d',
        position: 'relative'
      }}>
        {totalPages === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>
            <p>Aucune page trouvée pour ce chapitre.</p>
          </div>
        ) : readingMode === 'single' ? (
          /* Single Page Mode */
          <div 
            style={{
              position: 'relative',
              maxWidth: '100%',
              maxHeight: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              userSelect: 'none'
            }}
          >
            {isImageLoading && (
              <div style={{
                position: 'absolute',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                color: 'var(--text-muted)'
              }}>
                <Loader2 className="animate-spin" size={28} color="var(--primary)" />
                <span>Chargement de la page...</span>
              </div>
            )}

            <img
              src={formatImageUrl(pages[currentPageIndex])}
              alt={`Page ${currentPageIndex + 1}`}
              onLoad={() => setIsImageLoading(false)}
              onError={(e) => {
                setIsImageLoading(false);
                if (e.target.src !== DEFAULT_PAGE_IMAGE) e.target.src = DEFAULT_PAGE_IMAGE;
              }}
              onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                const x = e.clientX - rect.left;
                if (x > rect.width / 2) {
                  handleNextPage();
                } else {
                  handlePrevPage();
                }
              }}
              style={{
                maxHeight: isFullscreen ? '94vh' : '82vh',
                maxWidth: '92vw',
                transform: `scale(${zoomLevel})`,
                transformOrigin: 'center center',
                transition: 'transform 0.15s ease',
                borderRadius: '4px',
                boxShadow: '0 8px 30px rgba(0,0,0,0.7)',
                cursor: 'pointer',
                display: isImageLoading ? 'none' : 'block'
              }}
            />

            {/* Click navigation overlays */}
            <div
              onClick={handlePrevPage}
              title="Page précédente"
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                bottom: 0,
                width: '15%',
                cursor: 'w-resize',
                zIndex: 2
              }}
            />
            <div
              onClick={handleNextPage}
              title="Page suivante"
              style={{
                position: 'absolute',
                right: 0,
                top: 0,
                bottom: 0,
                width: '15%',
                cursor: 'e-resize',
                zIndex: 2
              }}
            />
          </div>
        ) : (
          /* Webtoon Continuous Scroll Mode (Default) */
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '12px',
            width: '100%',
            maxWidth: '850px'
          }}>
            {pages.map((pageUrl, idx) => (
              <div 
                key={idx} 
                id={`webtoon-page-${idx}`}
                data-page-index={idx}
                className="webtoon-page-item"
                style={{ 
                  display: 'flex', 
                  flexDirection: 'column', 
                  alignItems: 'center',
                  width: '100%' 
                }}
              >
                <img
                  src={formatImageUrl(pageUrl)}
                  alt={`Page ${idx + 1}`}
                  loading="lazy"
                  style={{
                    width: '100%',
                    height: 'auto',
                    borderRadius: '4px',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.5)'
                  }}
                  onError={(e) => {
                    if (e.target.src !== DEFAULT_PAGE_IMAGE) e.target.src = DEFAULT_PAGE_IMAGE;
                  }}
                />
                <span style={{ fontSize: '0.75rem', color: '#8b949e', marginTop: '6px' }}>
                  Page {idx + 1} / {totalPages}
                </span>
              </div>
            ))}

            {/* End of chapter prompt */}
            <div style={{ padding: '30px', textAlign: 'center' }}>
              <p style={{ color: 'var(--text-muted)', marginBottom: '14px' }}>
                Fin du Chapitre {currentChapterNum}
              </p>
              {chapters.findIndex(c => c.num === currentChapterNum) < chapters.length - 1 && (
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    const currentIdx = chapters.findIndex(c => c.num === currentChapterNum);
                    setCurrentChapterNum(chapters[currentIdx + 1].num);
                  }}
                >
                  Passer au Chapitre Suivant <ChevronRight size={16} />
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
