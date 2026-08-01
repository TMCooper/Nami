import React, { useEffect } from 'react';
import { X, Download, CheckCircle, AlertCircle, Trash2, StopCircle, HardDrive } from 'lucide-react';

export default function DownloadManagerDrawer({ isOpen, onClose, downloads, onCancelTask, onClearCompleted }) {
  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 55,
      display: 'flex',
      justifyContent: 'flex-end',
      background: 'rgba(0, 0, 0, 0.6)',
      backdropFilter: 'blur(4px)'
    }} onClick={onClose}>
      <div
        className="glass-modal animate-fade-in"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '460px',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          borderLeft: '1px solid var(--border-color)',
          borderRadius: 0
        }}
      >
        {/* Drawer Header */}
        <div style={{
          padding: '20px 24px',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Download size={20} color="var(--primary)" />
            <h3 style={{ fontSize: '1.2rem', fontWeight: 700 }}>Téléchargements</h3>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              className="btn btn-secondary btn-icon"
              style={{ width: '36px', height: '36px' }}
              onClick={onClearCompleted}
              title="Nettoyer les éléments terminés"
            >
              <Trash2 size={16} />
            </button>
            <button
              className="btn btn-secondary btn-icon"
              style={{ width: '36px', height: '36px' }}
              onClick={onClose}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Downloads List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {(!downloads || downloads.length === 0) ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '80px' }}>
              <Download size={40} style={{ opacity: 0.3, marginBottom: '12px' }} />
              <p>Aucun téléchargement en cours ou récent.</p>
            </div>
          ) : (
            downloads.map((task) => {
              const isDownloading = task.status === 'downloading';
              const isCompleted = task.status === 'completed';
              const isError = task.status === 'error';

              return (
                <div
                  key={task.id}
                  className="glass"
                  style={{
                    padding: '16px',
                    borderRadius: 'var(--radius-md)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '10px',
                    border: isDownloading ? '1px solid var(--primary-glow)' : '1px solid var(--border-color)'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#fff' }}>{task.anime_title}</h4>
                      <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        {task.season} — Épisode {task.episode_num}
                      </p>
                    </div>

                    {isDownloading && (
                      <button
                        className="btn btn-secondary btn-icon"
                        style={{ width: '28px', height: '28px' }}
                        onClick={() => onCancelTask(task.id)}
                        title="Annuler"
                      >
                        <StopCircle size={14} color="var(--accent-pink)" />
                      </button>
                    )}
                  </div>

                  {/* Progress Bar */}
                  <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.1)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
                    <div style={{
                      width: `${task.progress || 0}%`,
                      height: '100%',
                      background: isCompleted ? 'var(--accent-green)' : isError ? 'var(--accent-pink)' : 'linear-gradient(90deg, var(--primary), var(--secondary))',
                      transition: 'width 0.3s ease'
                    }}></div>
                  </div>

                  {/* Status Footer */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.75rem' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: isCompleted ? 'var(--accent-green)' : isError ? 'var(--accent-pink)' : 'var(--text-muted)' }}>
                      {isCompleted && <CheckCircle size={12} />}
                      {isError && <AlertCircle size={12} />}
                      {task.status === 'queued' && 'En attente...'}
                      {task.status === 'downloading' && `${task.progress}% — ${task.speed}`}
                      {task.status === 'completed' && 'Téléchargement terminé'}
                      {task.status === 'error' && `Erreur: ${task.error_message}`}
                    </span>

                    {task.file_path && (
                      <span style={{ color: 'var(--text-dim)', fontSize: '0.7rem' }} title={task.file_path}>
                        <HardDrive size={10} style={{ display: 'inline', marginRight: '3px' }} />
                        {task.file_path.split(/[/\\]/).slice(-2).join('/')}
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
