const REPOSITORY = 'xhan145/roar';
const RELEASES_URL = 'https://github.com/xhan145/roar/releases';
const SHA256 = /^[0-9a-f]{64}$/;
const GITHUB_ASSET = /^https:\/\/github\.com\/xhan145\/roar\/releases\/download\//;

export function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 1) throw new TypeError('asset size must be positive');
  return `${(bytes / 1024 ** 2).toFixed(2)} MiB`;
}

export function formatDate(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.valueOf()) || !/^\d{4}-\d{2}-\d{2}T/.test(iso)) throw new TypeError('published date must be ISO');
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date);
}

function validAvailable(record, platform) {
  const fields = ['version', 'release_name', 'published_at', 'architecture', 'package_type', 'asset_name', 'asset_url', 'asset_size_bytes', 'sha256', 'release_notes_url'];
  if (!record || record.available !== true || !['stable', 'preview'].includes(record.channel) || fields.some((field) => record[field] === undefined)) return false;
  if (fields.filter((field) => field !== 'asset_size_bytes').some((field) => typeof record[field] !== 'string' || record[field] === '')) return false;
  if (!Number.isInteger(record.asset_size_bytes) || record.asset_size_bytes < 1 || !SHA256.test(record.sha256)) return false;
  if (!/^\d{4}-\d{2}-\d{2}T.*Z$/.test(record.published_at) || Number.isNaN(new Date(record.published_at).valueOf())) return false;
  if (!GITHUB_ASSET.test(record.asset_url) || !/^https:\/\/github\.com\/xhan145\/roar\/releases\/tag\//.test(record.release_notes_url)) return false;
  if (platform === 'linux' && (!Array.isArray(record.tested_environments) || typeof record.known_limitations_url !== 'string')) return false;
  return true;
}

export function parseManifest(value) {
  if (!value || value.schema_version !== 1 || value.repository !== REPOSITORY || !value.platforms) throw new TypeError('unsupported release manifest');
  for (const platform of ['windows', 'linux']) {
    const record = value.platforms[platform];
    if (!record || !['stable', 'preview'].includes(record.channel)) throw new TypeError(`missing ${platform} channel`);
    if (record.available === false) continue;
    if (!validAvailable(record, platform)) throw new TypeError(`invalid ${platform} release metadata`);
  }
  return value;
}

export function platformView(record) {
  if (!record.available) {
    const name = record.channel === 'preview' ? 'Linux Preview' : 'Windows Stable';
    return { available: false, channel: record.channel, actionLabel: `${name} unavailable` };
  }
  return { available: true, channel: record.channel, actionLabel: `Download ${record.asset_name}`, version: `v${record.version}`, date: formatDate(record.published_at), packageType: record.package_type, architecture: record.architecture, size: formatBytes(record.asset_size_bytes), checksum: record.sha256, checksumLabel: `${record.sha256.slice(0, 11)}…${record.sha256.slice(-8)}`, releaseNotesUrl: record.release_notes_url, assetUrl: record.asset_url, testedEnvironments: record.tested_environments || [], limitationsUrl: record.known_limitations_url };
}

export async function writeChecksum(write, checksum) {
  if (typeof write !== 'function') return false;
  try {
    await write(checksum);
    return true;
  } catch {
    return false;
  }
}

function setText(card, name, text) {
  const element = card.querySelector(`[data-release="${name}"]`);
  if (element) element.textContent = text;
}

function setUnavailable(card, message) {
  const view = platformView({ available: false, channel: card.dataset.releasePlatform === 'linux' ? 'preview' : 'stable' });
  setText(card, 'status', message || view.actionLabel);
  const action = card.querySelector('[data-release="action"]');
  action.textContent = view.actionLabel;
  action.setAttribute('aria-disabled', 'true');
  action.removeAttribute('href');
  const recovery = card.querySelector('[data-release="recovery"]');
  recovery.href = RELEASES_URL;
  recovery.hidden = false;
  card.querySelector('[data-release-copy="checksum"]').disabled = true;
}

function renderCard(card, record) {
  const view = platformView(record);
  if (!view.available) return setUnavailable(card);
  setText(card, 'status', record.channel === 'preview' ? 'Preview availability verified from releases.' : 'Verified release metadata loaded.');
  setText(card, 'version', view.version); setText(card, 'release-date', view.date); setText(card, 'package', view.packageType); setText(card, 'architecture', view.architecture); setText(card, 'size', view.size);
  const checksum = card.querySelector('[data-release="checksum"]');
  checksum.textContent = view.checksumLabel; checksum.dataset.fullChecksum = view.checksum; checksum.title = view.checksum;
  const action = card.querySelector('[data-release="action"]');
  action.textContent = view.actionLabel; action.href = view.assetUrl; action.removeAttribute('aria-disabled');
  card.querySelector('[data-release="release-notes"]').href = view.releaseNotesUrl;
  if (view.limitationsUrl) card.querySelector('[data-release="limitations"]').href = view.limitationsUrl;
  const environment = card.querySelector('[data-release="tested-environments"]');
  if (environment) environment.textContent = view.testedEnvironments.join(', ') || 'Package checks recorded in the release.';
}

async function copyChecksum(event) {
  const card = event.currentTarget.closest('[data-release-platform]');
  const checksum = card.querySelector('[data-release="checksum"]');
  const status = card.querySelector('[data-release="checksum-status"]');
  const copied = await writeChecksum(navigator.clipboard?.writeText?.bind(navigator.clipboard), checksum.dataset.fullChecksum);
  if (copied) {
    status.textContent = 'Checksum copied';
  } else {
    const selection = window.getSelection(); const range = document.createRange();
    range.selectNodeContents(checksum); selection.removeAllRanges(); selection.addRange(range);
    status.textContent = 'Copy unavailable; checksum selected for manual copy';
  }
}

async function bootstrap() {
  const cards = [...document.querySelectorAll('[data-release-platform]')];
  cards.forEach((card) => card.querySelector('[data-release-copy="checksum"]').addEventListener('click', copyChecksum));
  try {
    const response = await fetch('data/releases.json');
    if (!response.ok) throw new Error('manifest request failed');
    const manifest = parseManifest(await response.json());
    cards.forEach((card) => renderCard(card, manifest.platforms[card.dataset.releasePlatform]));
  } catch {
    cards.forEach((card) => setUnavailable(card, 'Release metadata is unavailable. Check Releases for a verified package.'));
  }
}

if (typeof document !== 'undefined') bootstrap();
