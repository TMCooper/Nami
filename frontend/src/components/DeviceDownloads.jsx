import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, FolderOpen, RotateCw, Smartphone, X } from 'lucide-react';
import {
  canPickFile, canPickFolder, episodeTitle, formatBytes, formatEta, formatSpeed, pickFile, pickFolder, saveIntoFile,
  saveIntoFolder, sendToBrowser
} from '../utils/deviceDownload';

const POLL_EVERY = 1000;      // ms between two looks at the episodes being prepared on the server
const PROGRESS_EVERY = 400;   // ms between two progress renders of a copy

const ACTIVE = ['preparing', 'transferring', 'waiting'];

// mode: 'file' (one episode, saved where the user chose), 'folder' (several, into the folder chosen for them)
// or 'browser' (no file system access: the browser's own downloads)
const toJob = (server, mode, request, destination = null) => ({
  id: server.id,
  anime: server.anime,
  season: server.season,
  version: server.version,
  num: server.num,
  source: server.source,
  mode,
  destination,
  request, // what to send again for a retry: { animeId, season, version }
  phase: 'preparing',
  progress: 0,
  speed: 0,
  eta: null,
  bytes: 0,
  total: 0,
  error: ''
});

// Episodes for this device: YoitsuWrap prepares them on the server (in parallel), then each one is
// copied here as soon as it is ready (one copy at a time)
export function useDeviceDownloads() {
  const [jobs, setJobs] = useState([]);
  const [folderName, setFolderName] = useState('');
  const jobsRef = useRef(jobs);
  jobsRef.current = jobs;
  const copyQueueRef = useRef([]);
  const copyingRef = useRef(false);
  const controllersRef = useRef(new Map());

  const update = (id, patch) => setJobs((list) => list.map((j) => (j.id === id ? { ...j, ...patch } : j)));
  const forget = (id) => fetch(`/api/device-download/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }).catch(() => {});

  const copyNext = async () => {
    if (copyingRef.current) return;
    copyingRef.current = true;
    while (copyQueueRef.current.length) {
      const job = copyQueueRef.current.shift();
      if (job.mode === 'browser') {
        // The browser's download manager takes it from here (the server removes the file later)
        sendToBrowser(job);
        update(job.id, { phase: 'sent', progress: 100 });
        await new Promise((resolve) => setTimeout(resolve, 1500)); // browsers drop downloads started together
        continue;
      }
      const controller = new AbortController();
      controllersRef.current.set(job.id, controller);
      update(job.id, { phase: 'transferring', progress: 0, bytes: 0, speed: 0, eta: null });
      const startedAt = Date.now();
      let shownAt = 0;
      try {
        const save = job.mode === 'file' ? saveIntoFile : saveIntoFolder;
        const bytes = await save(job.destination, job, {
          signal: controller.signal,
          onProgress: (b, total) => {
            const now = Date.now();
            if (now - shownAt < PROGRESS_EVERY) return;
            shownAt = now;
            const speed = b / Math.max((now - startedAt) / 1000, 0.1);
            update(job.id, { bytes: b, total, speed, progress: total ? (b / total) * 100 : 0, eta: total ? (total - b) / speed : null });
          }
        });
        update(job.id, { phase: 'done', bytes, total: bytes, progress: 100, speed: 0, eta: null });
        forget(job.id);
      } catch (err) {
        update(job.id, controller.signal.aborted ? { phase: 'cancelled' } : { phase: 'error', error: err?.message || 'Échec de la copie' });
      } finally {
        controllersRef.current.delete(job.id);
      }
    }
    copyingRef.current = false;
  };

  // Server side progress of the episodes being prepared
  const preparing = jobs.filter((j) => j.phase === 'preparing').map((j) => j.id).join(',');
  useEffect(() => {
    if (!preparing) return undefined;
    let cancelled = false;
    const poll = async () => {
      const params = new URLSearchParams();
      preparing.split(',').forEach((id) => params.append('id', id));
      try {
        const res = await fetch(`/api/device-download/jobs?${params}`);
        const data = res.ok ? await res.json() : null;
        if (cancelled || !data) return;
        const byId = new Map((data.jobs || []).map((s) => [s.id, s]));
        const ready = [];
        for (const j of jobsRef.current) {
          const s = byId.get(j.id);
          if (j.phase !== 'preparing') continue;
          if (!s) update(j.id, { phase: 'error', error: 'Le serveur a perdu ce téléchargement' });
          else if (s.status === 'completed') ready.push({ ...j, phase: 'waiting', progress: 0, speed: 0, eta: null, total: s.total });
          else if (s.status === 'error') update(j.id, { phase: 'error', error: s.error || 'Téléchargement impossible' });
          else if (s.status === 'cancelled') update(j.id, { phase: 'cancelled' });
          else update(j.id, { progress: s.progress, speed: s.speed, eta: s.eta, bytes: s.downloaded, total: s.total, queued: s.status === 'queued' });
        }
        ready.forEach((j) => update(j.id, j));
        if (ready.length) {
          copyQueueRef.current.push(...ready);
          copyNext();
        }
      } catch {
        // next look in a second
      }
    };
    const timer = setInterval(poll, POLL_EVERY);
    poll();
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [preparing]);

  // request: { animeId, season (fiche key), version, episodes: [nums], labels: { anime, season, version } }
  // Called from a click: the place is asked first, at every download (the pickers need the user's gesture)
  const start = async (request) => {
    if (!request?.episodes?.length) return { ok: false };
    let mode = 'browser';
    let destination = null;
    try {
      if (request.episodes.length === 1 && canPickFile()) {
        destination = await pickFile(episodeTitle(request.labels || {}, request.episodes[0]));
        mode = 'file';
        setFolderName(destination.name);
      } else if (canPickFolder()) {
        destination = await pickFolder();
        mode = 'folder';
        setFolderName(destination.name || 'Dossier choisi');
      }
    } catch (err) {
      if (err?.name === 'AbortError') return { ok: false }; // picker closed: nothing starts
    }
    const res = await fetch('/api/device-download/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ anime_id: request.animeId, season: request.season, version: request.version, episodes: request.episodes })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) return { ok: false, error: data.detail || `Erreur ${res.status}` };
    const retryOf = { animeId: request.animeId, season: request.season, version: request.version };
    setJobs((list) => [...list, ...(data.jobs || []).map((s) => toJob(s, mode, retryOf, destination))]);
    return { ok: true };
  };

  const cancel = (id) => {
    copyQueueRef.current = copyQueueRef.current.filter((j) => j.id !== id);
    controllersRef.current.get(id)?.abort();
    update(id, { phase: 'cancelled' });
    forget(id);
  };

  const retry = async (id) => {
    const job = jobsRef.current.find((j) => j.id === id);
    if (!job) return;
    forget(id);
    const res = await fetch('/api/device-download/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ anime_id: job.request.animeId, season: job.request.season, version: job.request.version, episodes: [job.num] })
    }).catch(() => null);
    const data = res ? await res.json().catch(() => ({})) : {};
    const fresh = res?.ok && data.jobs?.[0];
    setJobs((list) => list.map((j) => (j.id !== id ? j : fresh
      ? toJob(fresh, j.mode, j.request, j.destination)
      : { ...j, phase: 'error', error: data.detail || 'Nouvel essai impossible' })));
  };

  const clear = () => setJobs((list) => list.filter((j) => ACTIVE.includes(j.phase)));

  // Leaving the page stops the copies (and the episodes prepared for it are never fetched)
  const active = jobs.some((j) => ACTIVE.includes(j.phase));
  useEffect(() => {
    if (!active) return undefined;
    const warn = (e) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [active]);

  return { jobs, folderName, start, cancel, retry, clear };
}

const PHASE_TEXT = {
  waiting: 'Prêt, en attente de copie',
  done: 'Enregistré sur cet appareil',
  cancelled: 'Annulé',
  sent: 'Envoyé au gestionnaire de téléchargements du navigateur'
};

function JobProgress({ job }) {
  const preparing = job.phase === 'preparing';
  const label = preparing
    ? (job.queued ? 'En file sur le serveur' : 'Préparation par YoitsuWrap')
    : 'Copie vers cet appareil';
  const details = [
    `${Math.round(job.progress || 0)} %`,
    formatSpeed(job.speed),
    job.eta != null && job.eta >= 0 ? `${formatEta(job.eta)} restantes` : '',
    job.total ? `${formatBytes(job.bytes)} / ${formatBytes(job.total)}` : ''
  ].filter(Boolean).join(' · ');
  return (
    <>
      <div className={`progress-track${job.progress ? '' : ' indeterminate'}`}>
        <div style={{ width: job.progress ? `${Math.max(2, job.progress)}%` : undefined, background: preparing ? 'var(--accent-cyan)' : 'var(--yt-red)' }} />
      </div>
      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
        {label}{details ? ` · ${details}` : ''}
      </span>
    </>
  );
}

export default function DeviceDownloadsPanel({ jobs, folderName, cancel, retry, clear }) {
  const [open, setOpen] = useState(true);
  if (!jobs.length) return null;
  const running = jobs.filter((j) => ACTIVE.includes(j.phase)).length;
  const done = jobs.filter((j) => j.phase === 'done' || j.phase === 'sent').length;

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
                  <span style={{ flex: 1, minWidth: 0, fontSize: '0.8rem', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={`${job.anime} · ${job.season} · ${job.version.toUpperCase()} · ép. ${job.num}`}>
                    {job.anime} · {job.season} · {job.version.toUpperCase()} · ép. {job.num}
                  </span>
                  {(job.phase === 'error' || job.phase === 'cancelled') && (
                    <button type="button" className="card-action card-action-flat" style={{ width: '30px', height: '30px' }} onClick={() => retry(job.id)} aria-label="Réessayer" title="Réessayer">
                      <RotateCw size={14} />
                    </button>
                  )}
                  {ACTIVE.includes(job.phase) && (
                    <button type="button" className="card-action card-action-flat" style={{ width: '30px', height: '30px' }} onClick={() => cancel(job.id)} aria-label="Annuler" title="Annuler">
                      <X size={14} />
                    </button>
                  )}
                </div>
                {job.phase === 'preparing' || job.phase === 'transferring' ? (
                  <JobProgress job={job} />
                ) : (
                  <span style={{ fontSize: '0.72rem', color: job.phase === 'error' ? '#ff6b6b' : job.phase === 'done' ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                    {job.phase === 'error' ? job.error : PHASE_TEXT[job.phase]}
                    {job.phase === 'done' && job.bytes ? ` · ${formatBytes(job.bytes)}` : ''}
                  </span>
                )}
              </li>
            ))}
          </ul>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px', borderTop: '1px solid var(--border-color)', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)', flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: '5px' }}>
              <FolderOpen size={13} />
              {folderName ? `Dernier enregistrement : ${folderName}` : 'Dossier de téléchargement du navigateur'}
            </span>
            <button type="button" className="chip" onClick={clear} style={{ marginLeft: 'auto' }} disabled={!jobs.some((j) => !ACTIVE.includes(j.phase))}>
              Effacer les terminés
            </button>
          </div>
        </>
      )}
    </div>
  );
}
