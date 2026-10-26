// Episodes saved on the viewer's own device (not on the server).
// Chromium on computers (Chrome, Edge, Opera) can write into a folder the user picks:
// <folder>/<anime>/<season>/<version>/ep_<n>.mp4. Elsewhere (Firefox, Safari, phones) the browser's own
// download manager receives each file, named "<anime> - <season> - <version> - ep_<n>.mp4".

export const canPickFolder = () => typeof window !== 'undefined' && typeof window.showDirectoryPicker === 'function';

// Names valid on Windows, macOS, Android and iOS file systems
export const safeName = (name) => (String(name || '')
  .replace(/[\\/:*?"<>|\u0000-\u001f]/g, ' ')
  .replace(/\s+/g, ' ')
  .replace(/^[\s.]+|[\s.]+$/g, '')
  .slice(0, 120)) || 'Sans titre';

export const episodeFileName = (num) => `ep_${safeName(num)}.mp4`;
export const flatFileName = (job) =>
  `${safeName(job.anime)} - ${safeName(job.season)} - ${job.version} - ${episodeFileName(job.num)}`;

export const deviceDownloadUrl = (urls, name) => {
  const params = new URLSearchParams();
  urls.forEach((u) => params.append('url', u));
  params.set('name', name);
  return `/api/device-download?${params}`;
};

let folder = null; // chosen once per visit

export const currentFolder = () => folder;

export const pickFolder = async () => {
  // Must run from a click: the browser only opens the picker on a user gesture
  folder = await window.showDirectoryPicker({ id: 'nami-episodes', mode: 'readwrite', startIn: 'videos' });
  return folder;
};

// Writes one episode into <folder>/<anime>/<season>/<version>/ep_<n>.mp4 while it downloads
export async function saveIntoFolder(root, job, { signal, onProgress }) {
  let dir = root;
  for (const part of [job.anime, job.season, job.version]) {
    dir = await dir.getDirectoryHandle(safeName(part), { create: true });
  }
  const fileName = episodeFileName(job.num);
  const response = await fetch(deviceDownloadUrl(job.urls, fileName), { signal });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Erreur ${response.status}`);
  }
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
      onProgress?.(bytes);
    }
    await writable.close();
  } catch (err) {
    // A cancelled or broken download leaves no half file behind
    await writable.abort().catch(() => {});
    await dir.removeEntry(fileName).catch(() => {});
    throw err;
  }
  return bytes;
}

// Hands the file to the browser's download manager (it keeps going in the background)
export function sendToBrowser(job) {
  const name = flatFileName(job);
  const link = document.createElement('a');
  link.href = deviceDownloadUrl(job.urls, name);
  link.download = name;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export const formatBytes = (bytes) => {
  if (!bytes) return '0 Mo';
  const mb = bytes / (1024 * 1024);
  return mb >= 1024 ? `${(mb / 1024).toFixed(2)} Go` : `${mb.toFixed(mb >= 100 ? 0 : 1)} Mo`;
};
