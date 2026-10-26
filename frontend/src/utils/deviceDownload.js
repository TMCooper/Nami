// Episodes saved on the viewer's own device (not in the server's library).
// A browser cannot fetch the video hosts itself, so YoitsuWrap first downloads the episode on the server
// (with progress), then the page fetches the finished file:
// - Chromium on computers (Chrome, Edge, Opera) writes it into a folder the user picks:
//   <folder>/<anime>/<season>/<version>/ep_<n>.mp4;
// - elsewhere (Firefox, Safari, phones) the browser's own download manager receives it,
//   named "<anime> - <season> - <version> - ep_<n>.mp4".

export const canPickFolder = () => typeof window !== 'undefined' && typeof window.showDirectoryPicker === 'function';

// Names valid on Windows, macOS, Android and iOS file systems
export const safeName = (name) => (String(name || '')
  .replace(/[\\/:*?"<>|\u0000-\u001f]/g, ' ')
  .replace(/\s+/g, ' ')
  .replace(/^[\s.]+|[\s.]+$/g, '')
  .slice(0, 120)) || 'Sans titre';

export const episodeFileName = (num) => `ep_${safeName(num)}.mp4`;

export const jobFileUrl = (id) => `/api/device-download/jobs/${encodeURIComponent(id)}/file`;

let folder = null; // chosen once per visit

export const currentFolder = () => folder;

export const pickFolder = async () => {
  // Must run from a click: the browser only opens the picker on a user gesture
  folder = await window.showDirectoryPicker({ id: 'nami-episodes', mode: 'readwrite', startIn: 'videos' });
  return folder;
};

// Copies one prepared episode into <folder>/<anime>/<season>/<version>/ep_<n>.mp4
export async function saveIntoFolder(root, job, { signal, onProgress }) {
  let dir = root;
  for (const part of [job.anime, job.season, job.version.toUpperCase()]) {
    dir = await dir.getDirectoryHandle(safeName(part), { create: true });
  }
  const fileName = episodeFileName(job.num);
  const response = await fetch(jobFileUrl(job.id), { signal });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Erreur ${response.status}`);
  }
  const total = Number(response.headers.get('content-length')) || 0;
  const file = await dir.getFileHandle(fileName, { create: true });
  const writable = await file.createWritable();
  const reader = response.body.getReader();
  let bytes = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      await writable.write(value);
      bytes += value.byteLength;
      onProgress?.(bytes, total);
    }
    await writable.close();
  } catch (err) {
    // A cancelled or broken copy leaves no half file behind
    await writable.abort().catch(() => {});
    await dir.removeEntry(fileName).catch(() => {});
    throw err;
  }
  return bytes;
}

// Hands the prepared file to the browser's download manager (it keeps going in the background)
export function sendToBrowser(job) {
  const link = document.createElement('a');
  link.href = jobFileUrl(job.id);
  link.rel = 'noopener';
  link.download = ''; // the server names it
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export const formatBytes = (bytes) => {
  if (!bytes) return '0 Mo';
  const mb = bytes / (1024 * 1024);
  return mb >= 1024 ? `${(mb / 1024).toFixed(2)} Go` : `${mb.toFixed(mb >= 100 ? 0 : 1)} Mo`;
};

export const formatSpeed = (bps) => {
  if (!bps) return '';
  const mb = bps / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} Mo/s` : `${Math.round(bps / 1024)} Ko/s`;
};

export const formatEta = (seconds) => {
  if (seconds == null || seconds < 0) return '';
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const min = Math.floor(seconds / 60);
  return min < 60 ? `${min} min ${String(Math.round(seconds % 60)).padStart(2, '0')}` : `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, '0')}`;
};
