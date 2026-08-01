import React, { useState, useEffect } from 'react';
import { X, Save, Check, HardDrive } from 'lucide-react';

export default function SettingsModal({ isOpen, onClose }) {
  const [rootFolder, setRootFolder] = useState('/downloads');
  const [defaultProvider, setDefaultProvider] = useState('all');
  const [downloadQuality, setDownloadQuality] = useState('1080p');
  const [isSaved, setIsSaved] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    fetch('/api/settings')
      .then((res) => res.json())
      .then((data) => {
        if (data.root_folder) setRootFolder(data.root_folder);
        if (data.default_provider) setDefaultProvider(data.default_provider);
        if (data.download_quality) setDownloadQuality(data.download_quality);
      })
      .catch((err) => console.error("Error loading settings:", err));
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
      .then(() => {
        setIsSaved(true);
        setTimeout(() => setIsSaved(false), 2500);
      })
      .catch((err) => console.error("Error saving settings:", err));
  };

  if (!isOpen) return null;

  const inputStyle = {
    width: '100%',
    padding: '10px 14px',
    background: '#0D1117',
    border: '1px solid var(--border-color)',
    borderRadius: 'var(--radius-sm)',
    color: '#fff',
    fontSize: '0.88rem',
    outline: 'none'
  };

  const labelStyle = {
    display: 'block',
    fontSize: '0.88rem',
    fontWeight: 600,
    marginBottom: '6px',
    color: '#fff'
  };

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 60,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px',
      background: 'rgba(0, 0, 0, 0.7)',
      backdropFilter: 'blur(6px)'
    }} onClick={onClose}>
      <div
        className="surface animate-fade-in"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '500px',
          borderRadius: 'var(--radius-md)',
          padding: '24px'
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3 style={{ fontSize: '1.2rem', fontWeight: 800 }}>Paramètres</h3>
          <button className="btn btn-icon btn-secondary" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        {/* Form */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          {/* Root Folder */}
          <div>
            <label style={labelStyle}>
              <HardDrive size={14} style={{ display: 'inline', marginRight: '6px', color: 'var(--accent-cyan)' }} />
              Dossier Racine (Root Folder)
            </label>
            <input
              type="text"
              value={rootFolder}
              onChange={(e) => setRootFolder(e.target.value)}
              placeholder="ex: /media/tmcooper/Elements ou D:/root folder"
              style={inputStyle}
            />
            <div style={{ marginTop: '6px', padding: '8px 12px', background: 'rgba(0, 180, 216, 0.05)', borderRadius: 'var(--radius-sm)', border: '1px dashed rgba(0, 180, 216, 0.3)' }}>
              <code style={{ fontSize: '0.75rem', color: 'var(--accent-cyan)', wordBreak: 'break-all' }}>
                {rootFolder.trim() || '/downloads'}/nami/anime/[NomAnime]/[Saison]/[Episode].mp4
              </code>
            </div>
          </div>

          {/* Default Source */}
          <div>
            <label style={labelStyle}>Source par Défaut</label>
            <select value={defaultProvider} onChange={(e) => setDefaultProvider(e.target.value)} style={inputStyle}>
              <option value="all">Toutes les sources</option>
              <option value="anime_sama">Anime-Sama uniquement</option>
              <option value="voiranime">VoirAnime uniquement</option>
            </select>
          </div>

          {/* Quality */}
          <div>
            <label style={labelStyle}>Qualité Préférée</label>
            <select value={downloadQuality} onChange={(e) => setDownloadQuality(e.target.value)} style={inputStyle}>
              <option value="1080p">1080p (Full HD)</option>
              <option value="720p">720p (HD)</option>
              <option value="480p">480p (SD)</option>
            </select>
          </div>

          {/* Save Button */}
          <button
            className="btn btn-primary"
            onClick={handleSave}
            style={{ width: '100%', padding: '12px', marginTop: '8px' }}
          >
            {isSaved ? <><Check size={16} /> Enregistré !</> : <><Save size={16} /> Sauvegarder</>}
          </button>
        </div>
      </div>
    </div>
  );
}
