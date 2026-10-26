import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, FolderOpen, Loader2, RotateCw, Smartphone, X } from 'lucide-react';
import { canPickFolder, currentFolder, formatBytes, pickFolder, saveIntoFolder, sendToBrowser } from '../utils/deviceDownload';

const PROGRESS_EVERY = 400; // ms between two progress renders of one download

// Queue of episodes downloaded to this device: one at a time, written while they arrive
export function useDeviceDownloads() {
  const [jobs, setJobs] = useState([]);
  const [folderName, setFolderName] = useState('');
  const queueRef = useRef([]);
  const runningRef = useRef(false);
  const controllersRef = useRef(new Map());
  const counterRef = useRef(0);

  const update = (id, patch) => setJobs((list) => list.map((j) => (j.id === id ? { ...j, ...patch } : j)));

  const run = async () => {
    if (runningRef.current) return;
    runningRef.current = true;
    while (queueRef.current.length) {
      const job = queueRef.current.shift();
      const controller = new AbortController();
      controllersRef.current.set(job.id, controller);
      update(job.id, { status: 'running', bytes: 0, error: '' });
      let shownAt = 0;
      try {
        const bytes = await saveIntoFolder(currentFolder(), job, {
          signal: controller.signal,
          onProgress: (b) => {
            const now = Date.now();
            if (now - shownAt > PROGRESS_EVERY) {
              shownAt = now;
              update(job.id, { bytes: b });
            }
          }
        });
        update(job.id, { status: 'done', bytes });
      } catch (err) {
        update(job.id, controller.signal.aborted ? { status: 'cancelled' } : { status: 'error', error: err?.message || 'Échec' });
      } finally {
        controllersRef.current.delete(job.id);
      }
    }
    runningRef.current = false;
  };

  // items: [{ anime, season, version, num, urls }] — called from a click (the folder picker needs it)
  const start = async (items) => {
    if (!items?.length) return false;
    let mode = 'browser';
    if (canPickFolder()) {
      try {
        const root = currentFolder() || await pickFolder();
        setFolderName(root.name || 'Dossier choisi');
        mode = 'folder';
      } catch (err) {
        if (err?.name === 'AbortError') return false; // picker closed: nothing starts
      }
    }
    const created = items.map((item) => ({
      ...item,
      id: `dl-${++counterRef.current}`,
      status: mode === 'folder' ? 'queued' : 'sent',
      bytes: 0,
      error: '',
      mode
    }));
    setJobs((list) => [...list, ...created]);
    if (mode === 'folder') {
      queueRef.current.push(...created);
      run();
    } else {
      // Spaced out: browsers drop downloads started in the same instant
      created.forEach((job, i) => setTimeout(() => sendToBrowser(job), i * 1500));
    }
    return true;
  };

  const cancel = (id) => {
    queueRef.current = queueRef.current.filter((j) => j.id !== id);
    controllersRef.current.get(id)?.abort();
    update(id, { status: 'cancelled' });
  };

  const retry = (id) => {
    const job = jobs.find((j) => j.id === id);
    if (!job) return;
    if (job.mode === 'browser') {
      sendToBrowser(job);
      return;
    }
    update(id, { status: 'queued', error: '', bytes: 0 });
    queueRef.current.push(job);
    run();
  };

  const clear = () => setJobs((list) => list.filter((j) => j.status === 'queued' || j.status === 'running'));

  const changeFolder = async () => {
    try {
      const root = await pickFolder();
      setFolderName(root.name || 'Dossier choisi');
    } catch {
      // picker closed: keep the current folder
    }
  };

  // Leaving the page would cut the downloads being written
  const active = jobs.some((j) => j.status === 'queued' || j.status === 'running');
  useEffect(() => {
    if (!active) return undefined;
    const warn = (e) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [active]);

  return { jobs, folderName, start, cancel, retry, clear, changeFolder };
}

const STATUS_TEXT = {
  queued: 'En attente',
  done: 'Terminé',
  cancelled: 'Annulé',
  sent: 'Envoyé au gestionnaire de téléchargements du navigateur'
};

export default function DeviceDownloadsPanel({ jobs, folderName, cancel, retry, clear, changeFolder }) {
  const [open, setOpen] = useState(true);
  if (!jobs.length) return null;
  const running = jobs.filter((j) => j.status === 'queued' || j.status === 'running').length;
  const done = jobs.filter((j) => j.status === 'done' || j.status === 'sent').length;

  return (
    <div className="device-panel" role="region" aria-label="Téléchargements sur cet appareil">
      <button type="button" className="device-panel-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Smartphone size={16} />
        <span style={{ flex: 1, textAlign: 'left' }}>
          Sur cet appareil {running > 0 ? `· ${running} en cours` : `· ${done} terminé${done > 1 ? 's' : ''}`}
        </span>
        {open ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
      </button>

      {open && (
        <>
          <ul className="device-panel-list">
            {jobs.map((job) => (
              <li key={job.id} style={{ display: 'flex', flexDirection: 'column', gap: '5px', padding: '8px 12px', borderTop: '1px solid var(--border-color)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ flex: 1, minWidth: 0, fontSize: '0.8rem', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={`${job.anime} · ${job.season} · ${job.version} · ép. ${job.num}`}>
                    {job.anime} · {job.season} · {job.version} · ép. {job.num}
                  </span>
                  {(job.status === 'error' || job.status === 'cancelled') && (
                    <button type="button" className="card-action card-action-flat" style={{ width: '30px', height: '30px' }} onClick={() => retry(job.id)} aria-label="Réessayer" title="Réessayer">
                      <RotateCw size={14} />
                    </button>
                  )}
                  {(job.status === 'queued' || job.status === 'running') && (
                    <button type="button" className="card-action card-action-flat" style={{ width: '30px', height: '30px' }} onClick={() => cancel(job.id)} aria-label="Annuler" title="Annuler">
                      <X size={14} />
                    </button>
                  )}
                </div>
                {job.status === 'running' ? (
                  <>
                    <div className="progress-track indeterminate"><div /></div>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <Loader2 className="animate-spin" size={11} /> {formatBytes(job.bytes)} reçus
                    </span>
                  </>
                ) : (
                  <span style={{ fontSize: '0.72rem', color: job.status === 'error' ? '#ff6b6b' : job.status === 'done' ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                    {job.status === 'error' ? job.error : STATUS_TEXT[job.status]}
                    {job.status === 'done' && job.bytes ? ` · ${formatBytes(job.bytes)}` : ''}
                  </span>
                )}
              </li>
            ))}
          </ul>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px', borderTop: '1px solid var(--border-color)', flexWrap: 'wrap' }}>
            {folderName ? (
              <button type="button" className="chip" onClick={changeFolder} title="Changer de dossier">
                <FolderOpen size={14} /> {folderName}
              </button>
            ) : (
              <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)', flex: 1 }}>Dossier de téléchargement du navigateur</span>
            )}
            <button type="button" className="chip" onClick={clear} style={{ marginLeft: 'auto' }} disabled={!jobs.some((j) => j.status !== 'queued' && j.status !== 'running')}>
              Effacer les terminés
            </button>
          </div>
        </>
      )}
    </div>
  );
}
