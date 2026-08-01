import React from 'react';
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
      background: 'rgba(0, 0, 0, 0.5)',
      backdropFilter: 'blur(4px)'
    }} onClick={onClose}>
      <div
        className="surface animate-fade-in"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '420px',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          borderLeft: '1px solid var(--border-color)',
          borderRadius: 0
        }}
      >
        {/* Drawer Header */}
        <div style={{
          padding: '16px 20px',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Download size={18} color="var(--accent-cyan)" />
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Téléchargements</h3>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button className="btn btn-secondary btn-icon" style={{ width: '32px', height: '32px' }} onClick={onClearCompleted} title="Nettoyer">
              <Trash2 size={14} />
            </button>
            <button className="btn btn-secondary btn-icon" style={{ width: '32px', height: '32px' }} onClick={onClose}>
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Downloads List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {(!downloads || downloads.length === 0) ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '60px' }}>
              <Download size={36} style={{ opacity: 0.2, marginBottom: '10px' }} />
              <p style={{ fontSize: '0.88rem' }}>Aucun téléchargement.</p>
            </div>
          ) : (
            downloads.map((task) => {
              const isDownloading = task.status === 'downloading';
              const isCompleted = task.status === 'completed';
              const isError = task.status === 'error';

              return (
                <div
                  key={task.id}
                  className="surface-card"
                  style={{
                    padding: '12px',
                    borderRadius: 'var(--radius-sm)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <h4 style={{ fontSize: '0.88rem', fontWeight: 700, color: '#fff' }}>{task.anime_title}</h4>
                      <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {task.season} — Ép. {task.episode_num}
                      </p>
                    </div>
                    {isDownloading && (
                      <button className="btn btn-secondary btn-icon" style={{ width: '26px', height: '26px' }} onClick={() => onCancelTask(task.id)} title="Annuler">
                        <StopCircle size={12} color="var(--primary)" />
                      </button>
                    )}
                  </div>

                  {/* Progress Bar */}
                  <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.08)', borderRadius: 'var(--radius-full)', overflow: 'hidden' }}>
                    <div style={{
                      width: `${task.progress || 0}%`,
                      height: '100%',
                      background: isCompleted ? 'var(--accent-green)' : isError ? 'var(--primary)' : 'var(--accent-cyan)',
                      transition: 'width 0.3s ease'
                    }}></div>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.72rem' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: isCompleted ? 'var(--accent-green)' : isError ? 'var(--primary)' : 'var(--text-muted)' }}>
                      {isCompleted && <><CheckCircle size={11} /> Terminé</>}
                      {isError && <><AlertCircle size={11} /> Erreur</>}
                      {task.status === 'queued' && 'En attente...'}
                      {task.status === 'downloading' && `${task.progress}% — ${task.speed}`}
                      {task.status === 'cancelled' && 'Annulé'}
                    </span>
                    {task.file_path && (
                      <span style={{ color: 'var(--text-dim)', fontSize: '0.68rem' }} title={task.file_path}>
                        <HardDrive size={9} style={{ display: 'inline', marginRight: '2px' }} />
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
