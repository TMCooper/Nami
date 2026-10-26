import React, { useState, useEffect } from 'react';
import { X, Save, Check, HardDrive, RefreshCw, GitPullRequest, ArrowDownCircle, CheckCircle, ShieldCheck } from 'lucide-react';
import SourcesPanel from './SourcesPanel';

export default function SettingsModal({ isOpen, onClose, onSourcesChange }) {
  const [rootFolder, setRootFolder] = useState('/downloads');
  const [parallel, setParallel] = useState(3);
  const [downloadQuality, setDownloadQuality] = useState('1080p');
  const [isSaved, setIsSaved] = useState(false);

  // Updates State
  const [updates, setUpdates] = useState(null);
  const [isCheckingUpdates, setIsCheckingUpdates] = useState(false);
  const [updatingTarget, setUpdatingTarget] = useState(null);
  const [updateMsg, setUpdateMsg] = useState('');

  useEffect(() => {
    if (!isOpen) return;

    fetch('/api/settings')
      .then((res) => res.json())
      .then((data) => {
        if (data.root_folder) setRootFolder(data.root_folder);
        if (data.max_concurrent_downloads) setParallel(Number(data.max_concurrent_downloads));
        if (data.download_quality) setDownloadQuality(data.download_quality);
      })
      .catch((err) => console.error("Error loading settings:", err));

    checkUpdates();
  }, [isOpen]);

  const checkUpdates = () => {
    setIsCheckingUpdates(true);
    setUpdateMsg('');
    fetch('/api/updates/check')
      .then((res) => res.json())
      .then((data) => setUpdates(data))
      .catch((err) => console.error("Error checking updates:", err))
      .finally(() => setIsCheckingUpdates(false));
  };

  const handleApplyUpdate = (target) => {
    setUpdatingTarget(target);
    setUpdateMsg('Mise à jour en cours...');
    fetch(`/api/updates/apply?target=${target}`, { method: 'POST' })
      .then((res) => res.json())
      .then((data) => {
        setUpdateMsg('Mise à jour terminée avec succès !');
        checkUpdates();
      })
      .catch((err) => {
        console.error("Error applying update:", err);
        setUpdateMsg('Erreur lors de la mise à jour.');
      })
      .finally(() => setUpdatingTarget(null));
  };

  const handleSave = () => {
    fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        root_folder: rootFolder,
        max_concurrent_downloads: parallel,
        download_quality: downloadQuality
      })
    })
      .then((res) => res.json())
      .then(() => {
        setIsSaved(true);
        setTimeout(() => setIsSaved(false), 2500);
      })
      .catch((err) => console.error("Error saving settings:", err));
  };

  if (!isOpen) return null;

  const inputStyle = {
    width: '100%',
    padding: '9px 12px',
    background: '#0F0F0F',
    border: '1px solid var(--border-color)',
    borderRadius: 'var(--radius-sm)',
    color: '#fff',
    fontSize: '0.85rem',
    outline: 'none'
  };

  const labelStyle = {
    display: 'block',
    fontSize: '0.85rem',
    fontWeight: 600,
    marginBottom: '6px',
    color: '#fff'
  };

  return (
    <div className="modal-overlay" style={{
      position: 'fixed',
      inset: 0,
      zIndex: 60,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px',
      background: 'rgba(0, 0, 0, 0.8)',
      backdropFilter: 'blur(8px)'
    }} onClick={onClose}>
      <div
        className="surface animate-fade-in modal-sheet"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '580px',
          maxHeight: '90vh',
          overflowY: 'auto',
          borderRadius: 'var(--radius-md)',
          padding: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-color)'
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 800 }}>Paramètres & Maintenance</h3>
          <button className="btn btn-icon btn-secondary" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <SourcesPanel onChange={onSourcesChange} />

        {/* 1. Storage & Preferences */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--primary)', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '6px' }}>
            Stockage & Préférences
          </h4>

          {/* Root Folder */}
          <div>
            <label style={labelStyle}>
              <HardDrive size={14} style={{ display: 'inline', marginRight: '6px', color: 'var(--accent-cyan)' }} />
              Dossier Racine de Téléchargement (sur la machine hôte)
            </label>
            <input
              type="text"
              value={rootFolder}
              onChange={(e) => setRootFolder(e.target.value)}
              placeholder="ex: /downloads ou /media/pi/DisqueExt"
              style={inputStyle}
            />
            <div style={{ marginTop: '6px', padding: '6px 10px', background: 'rgba(0, 180, 216, 0.05)', borderRadius: 'var(--radius-sm)', border: '1px dashed rgba(0, 180, 216, 0.25)' }}>
              <code style={{ fontSize: '0.74rem', color: 'var(--accent-cyan)', wordBreak: 'break-all' }}>
                {rootFolder.trim() || '/downloads'}/nami/Anime/[Anime]/[Saison]/[version]/[n].mp4
              </code>
            </div>
          </div>

          <div className="form-grid-2" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label style={labelStyle} title="YoitsuWrap télécharge les épisodes d'une saison en même temps">Épisodes en parallèle</label>
              <select value={parallel} onChange={(e) => setParallel(Number(e.target.value))} style={inputStyle}>
                {[1, 2, 3, 4, 5, 6].map((n) => (
                  <option key={n} value={n}>{n} à la fois</option>
                ))}
              </select>
            </div>

            <div>
              <label style={labelStyle}>Qualité Vidéo</label>
              <select value={downloadQuality} onChange={(e) => setDownloadQuality(e.target.value)} style={inputStyle}>
                <option value="1080p">1080p (Full HD)</option>
                <option value="720p">720p (HD)</option>
                <option value="480p">480p (SD)</option>
              </select>
            </div>
          </div>

          <button
            className="btn btn-primary"
            onClick={handleSave}
            style={{ padding: '8px', fontSize: '0.82rem' }}
          >
            {isSaved ? <><Check size={14} /> Enregistré !</> : <><Save size={14} /> Enregistrer les préférences</>}
          </button>
        </div>

        {/* 2. In-App Updates & Maintenance */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '6px' }}>
            <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--accent-green)' }}>
              Mises à jour des APIs & Composants
            </h4>
            <button
              className="btn btn-secondary"
              style={{ fontSize: '0.74rem', padding: '3px 8px', gap: '4px' }}
              onClick={checkUpdates}
              disabled={isCheckingUpdates}
            >
              <RefreshCw size={12} className={isCheckingUpdates ? 'animate-spin' : ''} />
              <span>{isCheckingUpdates ? 'Vérification...' : 'Vérifier'}</span>
            </button>
          </div>

          {updateMsg && (
            <div style={{ padding: '8px 12px', background: 'rgba(46, 160, 67, 0.15)', border: '1px solid rgba(46, 160, 67, 0.3)', borderRadius: 'var(--radius-sm)', fontSize: '0.78rem', color: '#3FB950' }}>
              {updateMsg}
            </div>
          )}

          {updates && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {Object.entries(updates).map(([key, item]) => (
                <div
                  key={key}
                  style={{
                    background: '#0F0F0F',
                    border: '1px solid var(--border-color)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '10px 14px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '12px'
                  }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#fff' }}>{item.name}</span>
                    <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                      Version locale : <code style={{ color: '#58A6FF' }}>{item.current_version}</code> {item.latest_version && item.latest_version !== item.current_version && <>→ Dernière : <code style={{ color: '#3FB950' }}>{item.latest_version}</code></>}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {item.up_to_date ? (
                      <span className="badge" style={{ background: 'rgba(46, 160, 67, 0.15)', color: '#3FB950', fontSize: '0.72rem' }}>
                        ✓ À jour
                      </span>
                    ) : (
                      <button
                        className="btn btn-primary"
                        style={{ fontSize: '0.74rem', padding: '4px 10px', gap: '4px' }}
                        disabled={updatingTarget !== null}
                        onClick={() => handleApplyUpdate(key)}
                      >
                        <ArrowDownCircle size={12} />
                        <span>{updatingTarget === key ? 'Installation...' : 'Mettre à jour'}</span>
                      </button>
                    )}
                  </div>
                </div>
              ))}

              <button
                className="btn btn-secondary"
                style={{ width: '100%', padding: '8px', fontSize: '0.8rem', gap: '6px', marginTop: '4px' }}
                disabled={updatingTarget !== null}
                onClick={() => handleApplyUpdate('all')}
              >
                <GitPullRequest size={14} />
                <span>{updatingTarget === 'all' ? 'Mise à jour globale...' : 'Tout mettre à jour (APIs & Wrapper)'}</span>
              </button>
            </div>
          )}

          <div style={{
            background: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-sm)',
            padding: '10px 12px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '0.75rem',
            color: 'var(--text-muted)'
          }}>
            <ShieldCheck size={16} color="var(--accent-green)" style={{ flexShrink: 0 }} />
            <span>
              Les mises à jour des dépôts et bibliothèques n'affectent jamais vos utilisateurs, vos réglages ni vos vidéos téléchargées (dossier <code style={{ color: '#fff' }}>/data</code> protégé).
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
