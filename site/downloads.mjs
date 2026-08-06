const REPOSITORY = 'xhan145/roar';
const RELEASES_URL = 'https://github.com/xhan145/roar/releases';
const SHA256 = /^[0-9a-f]{64}$/;
const VERSION = /^\d+\.\d+\.\d+$/;

export function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 1) throw new TypeError('asset size must be positive');
  return `${(bytes / 1024 ** 2).toFixed(2)} MiB`;
}

export function formatDate(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.valueOf()) || !/^\d{4}-\d{2}-\d{2}T/.test(iso)) throw new TypeError('published date must be ISO');
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date);
}

function isValidUtcDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?Z$/.exec(value);
  if (!match) return false;
  const [year, month, day, hour, minute, second] = match.slice(1).map(Number);
  return month >= 1 && month <= 12 && day >= 1 && day <= new Date(Date.UTC(year, month, 0)).getUTCDate()
    && hour <= 23 && minute <= 59 && second <= 59;
}

function isTrustedAssetUrl(value, version, assetName) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.host === 'github.com'
      && url.pathname === `/xhan145/roar/releases/download/v${version}/${assetName}`;
  } catch {
    return false;
  }
}

function isReleaseNotesUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.host === 'github.com'
      && url.pathname.startsWith('/xhan145/roar/releases/tag/');
  } catch {
    return false;
  }
}

function validAvailable(record, platform) {
  const fields = ['version', 'release_name', 'published_at', 'architecture', 'package_type', 'asset_name', 'asset_url', 'asset_size_bytes', 'sha256', 'release_notes_url'];
  const expected = new Set(['available', 'channel', ...fields]);
  if (platform === 'linux') { expected.add('tested_environments'); expected.add('known_limitations_url'); }
  if (!record || record.available !== true || Object.keys(record).length !== expected.size || Object.keys(record).some((key) => !expected.has(key)) || fields.some((field) => record[field] === undefined)) return false;
  if (fields.filter((field) => field !== 'asset_size_bytes').some((field) => typeof record[field] !== 'string' || record[field] === '')) return false;
  if (!Number.isInteger(record.asset_size_bytes) || record.asset_size_bytes < 1 || !SHA256.test(record.sha256)) return false;
  if (!VERSION.test(record.version) || !isValidUtcDate(record.published_at) || !isReleaseNotesUrl(record.release_notes_url)) return false;
  const contract = platform === 'windows'
    ? { channel: 'stable', packageType: 'exe', asset: `ROAR-Setup-${record.version}.exe` }
    : { channel: 'preview', packageType: 'AppImage', asset: `ROAR-Linux-${record.version}-x86_64.AppImage` };
  if (record.channel !== contract.channel || record.architecture !== 'x86_64' || record.package_type !== contract.packageType || record.asset_name !== contract.asset || !isTrustedAssetUrl(record.asset_url, record.version, record.asset_name)) return false;
  if (platform === 'linux' && (!Array.isArray(record.tested_environments) || !record.tested_environments.length || !record.tested_environments.every((environment) => typeof environment === 'string' && environment) || record.known_limitations_url !== '/linux/')) return false;
  return true;
}

export function parseManifest(value) {
  const manifestKeys = ['schema_version', 'repository', 'generated_at', 'platforms'];
  if (!value || Object.keys(value).length !== manifestKeys.length || manifestKeys.some((key) => !(key in value)) || value.schema_version !== 1 || value.repository !== REPOSITORY || !value.platforms || !isValidUtcDate(value.generated_at)) throw new TypeError('unsupported release manifest');
  if (Object.keys(value.platforms).length !== 2 || !('windows' in value.platforms) || !('linux' in value.platforms)) throw new TypeError('invalid platform records');
  for (const platform of ['windows', 'linux']) {
    const record = value.platforms[platform];
    const channel = platform === 'windows' ? 'stable' : 'preview';
    if (!record || record.channel !== channel) throw new TypeError(`missing ${platform} channel`);
    if (record.available === false && Object.keys(record).length === 2) continue;
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

export function manuallySelectChecksum(checksum, status, selection, range) {
  checksum.textContent = checksum.dataset.fullChecksum;
  range.selectNodeContents(checksum);
  selection.removeAllRanges();
  selection.addRange(range);
  status.textContent = 'Copy unavailable; checksum selected for manual copy';
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
    manuallySelectChecksum(checksum, status, selection, range);
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
