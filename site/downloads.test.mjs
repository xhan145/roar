import assert from 'node:assert/strict';
import test from 'node:test';

import { formatBytes, formatDate, manuallySelectChecksum, parseManifest, platformView, writeChecksum } from './downloads.mjs';

const windows = {
  available: true, channel: 'stable', version: '0.35.2',
  release_name: 'ROAR v0.35.2', published_at: '2026-08-03T19:20:31Z',
  architecture: 'x86_64', package_type: 'exe', asset_name: 'ROAR-Setup-0.35.2.exe',
  asset_url: 'https://github.com/xhan145/roar/releases/download/v0.35.2/ROAR-Setup-0.35.2.exe',
  asset_size_bytes: 908794228,
  sha256: 'ed7180f00bd4a3c923c97eeb8b84c43f263b0fced9aa38d903489eed4ad768e3',
  release_notes_url: 'https://github.com/xhan145/roar/releases/tag/v0.35.2',
};

const linux = {
  ...windows, channel: 'preview', package_type: 'AppImage',
  asset_name: 'ROAR-Linux-0.35.2-x86_64.AppImage',
  asset_url: 'https://github.com/xhan145/roar/releases/download/v0.35.2/ROAR-Linux-0.35.2-x86_64.AppImage',
  tested_environments: ['Ubuntu 24.04 (x86_64, X11)'], known_limitations_url: '/linux/',
};

function manifest(platforms) {
  return { schema_version: 1, repository: 'xhan145/roar', generated_at: '2026-08-06T12:00:00Z', platforms };
}

test('formatBytes reports exact binary size without calling a large file small', () => {
  assert.equal(formatBytes(908794228), '866.69 MiB');
});

test('formatDate renders an ISO timestamp in UTC', () => {
  assert.equal(formatDate('2026-08-03T19:20:31Z'), '3 Aug 2026');
});

test('parseManifest accepts the verified repository and both platform channels', () => {
  assert.deepEqual(parseManifest(manifest({ windows, linux: { available: false, channel: 'preview' } })).platforms.windows, windows);
});

test('parseManifest rejects an unsupported schema version', () => {
  assert.throws(() => parseManifest({ ...manifest({ windows, linux: { available: false, channel: 'preview' } }), schema_version: 2 }));
});

test('parseManifest rejects extra schema fields instead of ignoring them', () => {
  assert.throws(() => parseManifest({ ...manifest({ windows, linux: { available: false, channel: 'preview' } }), extra: true }));
});

test('parseManifest rejects malformed available metadata', () => {
  assert.throws(() => parseManifest({ schema_version: 1, repository: 'xhan145/roar', platforms: { windows: { ...windows, sha256: 'bad' }, linux: { available: false, channel: 'preview' } } }));
});

test('parseManifest rejects an available record with a non-UTC release date', () => {
  assert.throws(() => parseManifest(manifest({ windows: { ...windows, published_at: 'tomorrow' }, linux: { available: false, channel: 'preview' } })));
});

test('parseManifest rejects a normalized-but-invalid UTC calendar date', () => {
  assert.throws(() => parseManifest(manifest({ windows: { ...windows, published_at: '2026-02-31T19:20:31Z' }, linux: { available: false, channel: 'preview' } })));
});

test('parseManifest rejects platform-swapped channels and packages', () => {
  assert.throws(() => parseManifest(manifest({ windows: linux, linux: { available: false, channel: 'preview' } })));
  assert.throws(() => parseManifest(manifest({ windows, linux: { ...linux, channel: 'stable' } })));
});

test('unavailable channels produce a disabled recovery view', () => {
  assert.deepEqual(platformView({ available: false, channel: 'preview' }), {
    available: false, channel: 'preview', actionLabel: 'Linux Preview unavailable',
  });
});

test('Linux preview view keeps tested environments and the full digest available for copying', () => {
  const view = platformView(linux);
  assert.equal(view.checksum, windows.sha256);
  assert.equal(view.checksumLabel, 'ed7180f00bd…4ad768e3');
  assert.deepEqual(view.testedEnvironments, ['Ubuntu 24.04 (x86_64, X11)']);
});

test('writeChecksum fails closed when clipboard access is unavailable or rejected', async () => {
  assert.equal(await writeChecksum(undefined, windows.sha256), false);
  assert.equal(await writeChecksum(async () => { throw new Error('denied'); }, windows.sha256), false);
});

test('manual checksum fallback selects the complete digest and announces the exact recovery status', () => {
  const checksum = { textContent: 'ed7180f00bd…4ad768e3', dataset: { fullChecksum: windows.sha256 } };
  const status = { textContent: '' };
  const range = { selected: null, selectNodeContents(node) { this.selected = node; } };
  const selection = { cleared: false, added: null, removeAllRanges() { this.cleared = true; }, addRange(value) { this.added = value; } };

  manuallySelectChecksum(checksum, status, selection, range);

  assert.equal(checksum.textContent, windows.sha256);
  assert.equal(range.selected, checksum);
  assert.equal(selection.added, range);
  assert.equal(status.textContent, 'Copy unavailable; checksum selected for manual copy');
});

test('bootstrap enables checksum copying after a verified Windows release loads', async () => {
  const checksumCopy = { disabled: true, addEventListener() {} };
  const elements = {
    '[data-release="status"]': { textContent: '' },
    '[data-release="version"]': { textContent: '' },
    '[data-release="release-date"]': { textContent: '' },
    '[data-release="package"]': { textContent: '' },
    '[data-release="architecture"]': { textContent: '' },
    '[data-release="size"]': { textContent: '' },
    '[data-release="checksum"]': { textContent: '', dataset: {}, title: '' },
    '[data-release="action"]': { textContent: '', removeAttribute() {} },
    '[data-release="release-notes"]': { href: '' },
    '[data-release="tested-environments"]': null,
    '[data-release-copy="checksum"]': checksumCopy,
  };
  const card = {
    dataset: { releasePlatform: 'windows' },
    querySelector(selector) { return elements[selector]; },
  };
  const previousDocument = globalThis.document;
  const previousFetch = globalThis.fetch;
  globalThis.document = { querySelectorAll() { return [card]; } };
  globalThis.fetch = async () => ({
    ok: true,
    async json() {
      return manifest({ windows, linux: { available: false, channel: 'preview' } });
    },
  });

  try {
    await import(`./downloads.mjs?available-windows=${Date.now()}`);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(checksumCopy.disabled, false);
  } finally {
    globalThis.document = previousDocument;
    globalThis.fetch = previousFetch;
  }
});
