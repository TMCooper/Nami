import React, { useState, useEffect } from 'react';
import { X, Folder, Save, Check, HardDrive } from 'lucide-react';

export default function SettingsModal({ isOpen, onClose, onSettingsUpdated }) {
  const [rootFolder, setRootFolder] = useState('/downloads');
  const [defaultProvider, setDefaultProvider] = useState('all');
  const [downloadQuality, setDownloadQuality] = useState('1080p');
  const [isSaved, setIsSaved] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!isOpen) return;
    setIsLoading(true);

    fetch('/api/settings')
      .then((res) => res.json())
      .then((data) => {
        if (data.root_folder) setRootFolder(data.root_folder);
        if (data.default_provider) setDefaultProvider(data.default_provider);
        if (data.download_quality) setDownloadQuality(data.download_quality);
      })
      .catch((err) => console.error("Error loading settings:", err))
      .finally(() => setIsLoading(false));
  }, [isOpen]);

  const handleSave = () => {
    fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        root_folder: rootFolder,
        default_provider: defaultProvider,
        download_quality: downloadQuality
      })
    })
      .then((res) => res.json())
      .then((data) => {
        setIsSaved(true);
        if (onSettingsUpdated) onSettingsUpdated(data);
        setTimeout(() => setIsSaved(false), 2500);
      })
      .catch((err) => console.error("Error saving settings:", err));
  };

  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 60,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px',
      background: 'rgba(0, 0, 0, 0.7)',
      backdropFilter: 'blur(10px)'
    }} onClick={onClose}>
      <div
        className="glass-modal animate-fade-in"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '560px',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden',
          padding: '28px'
        }}
      >
        {/* Modal Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <h3 style={{ fontSize: '1.3rem', fontWeight: 800 }}>Paramètres Nami</h3>
          <button className="btn btn-icon btn-secondary" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Form Body */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Root Folder Option */}
          <div>
            <label style={{ display: 'block', fontSize: '0.9rem', fontWeight: 600, marginBottom: '8px', color: '#fff' }}>
              <HardDrive size={16} style={{ display: 'inline', marginRight: '6px', color: 'var(--primary)' }} />
              Dossier Racine de Téléchargement (Root Folder)
            </label>
            <input
              type="text"
              value={rootFolder}
              onChange={(e) => setRootFolder(e.target.value)}
              placeholder="ex: D:/root folder ou /downloads"
              style={{
                width: '100%',
                padding: '12px 16px',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                color: '#fff',
                fontSize: '0.9rem',
                outline: 'none'
              }}
            />
            {/* Folder Structure Preview */}
            <div style={{ marginTop: '8px', padding: '10px 14px', background: 'rgba(0, 240, 255, 0.05)', borderRadius: 'var(--radius-sm)', border: '1px dashed var(--border-glow)' }}>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Arborescence générée :
              </p>
              <code style={{ fontSize: '0.78rem', color: 'var(--primary)', wordBreak: 'break-all' }}>
                {rootFolder.trim() || '/downloads'}/nami/anime/[NomAnime]/[Saison]/[Episode].mp4
              </code>
            </div>
          </div>

          {/* Default Source Option */}
          <div>
            <label style={{ display: 'block', fontSize: '0.9rem', fontWeight: 600, marginBottom: '8px', color: '#fff' }}>
              Source par Défaut
            </label>
            <select
              value={defaultProvider}
              onChange={(e) => setDefaultProvider(e.target.value)}
              style={{
                width: '100%',
                padding: '12px 16px',
                background: '#121826',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                color: '#fff',
                fontSize: '0.9rem',
                outline: 'none'
              }}
            >
              <option value="all">Toutes les sources (Anime-Sama + VoirAnime)</option>
              <option value="anime_sama">Anime-Sama uniquement</option>
              <option value="voiranime">VoirAnime uniquement</option>
            </select>
          </div>

          {/* Quality Preference */}
          <div>
            <label style={{ display: 'block', fontSize: '0.9rem', fontWeight: 600, marginBottom: '8px', color: '#fff' }}>
              Qualité de Téléchargement Préférée
            </label>
            <select
              value={downloadQuality}
              onChange={(e) => setDownloadQuality(e.target.value)}
              style={{
                width: '100%',
                padding: '12px 16px',
                background: '#121826',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                color: '#fff',
                fontSize: '0.9rem',
                outline: 'none'
              }}
            >
              <option value="1080p">1080p (Full HD)</option>
              <option value="720p">720p (HD)</option>
              <option value="480p">480p (SD)</option>
            </select>
          </div>

          {/* Save Button */}
          <button
            className="btn btn-primary"
            onClick={handleSave}
            style={{ width: '100%', padding: '14px', marginTop: '10px' }}
          >
            {isSaved ? (
              <>
                <Check size={18} /> Paramètres Enregistrés !
              </>
            ) : (
              <>
                <Save size={18} /> Sauvegarder les modifications
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
