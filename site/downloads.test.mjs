import assert from 'node:assert/strict';
import test from 'node:test';

import { formatBytes, formatDate, parseManifest, platformView, writeChecksum } from './downloads.mjs';

const windows = {
  available: true, channel: 'stable', version: '0.35.2',
  release_name: 'ROAR v0.35.2', published_at: '2026-08-03T19:20:31Z',
  architecture: 'x86_64', package_type: 'exe', asset_name: 'ROAR-Setup-0.35.2.exe',
  asset_url: 'https://github.com/xhan145/roar/releases/download/v0.35.2/ROAR-Setup-0.35.2.exe',
  asset_size_bytes: 908794228,
  sha256: 'ed7180f00bd4a3c923c97eeb8b84c43f263b0fced9aa38d903489eed4ad768e3',
  release_notes_url: 'https://github.com/xhan145/roar/releases/tag/v0.35.2',
};

test('formatBytes reports exact binary size without calling a large file small', () => {
  assert.equal(formatBytes(908794228), '866.69 MiB');
});

test('formatDate renders an ISO timestamp in UTC', () => {
  assert.equal(formatDate('2026-08-03T19:20:31Z'), '3 Aug 2026');
});

test('parseManifest accepts the verified repository and both platform channels', () => {
  assert.deepEqual(parseManifest({ schema_version: 1, repository: 'xhan145/roar', platforms: { windows, linux: { available: false, channel: 'preview' } } }).platforms.windows, windows);
});

test('parseManifest rejects an unsupported schema version', () => {
  assert.throws(() => parseManifest({ schema_version: 2, repository: 'xhan145/roar', platforms: { windows, linux: { available: false, channel: 'preview' } } }));
});

test('parseManifest rejects malformed available metadata', () => {
  assert.throws(() => parseManifest({ schema_version: 1, repository: 'xhan145/roar', platforms: { windows: { ...windows, sha256: 'bad' }, linux: { available: false, channel: 'preview' } } }));
});

test('parseManifest rejects an available record with a non-UTC release date', () => {
  assert.throws(() => parseManifest({ schema_version: 1, repository: 'xhan145/roar', platforms: { windows: { ...windows, published_at: 'tomorrow' }, linux: { available: false, channel: 'preview' } } }));
});

test('unavailable channels produce a disabled recovery view', () => {
  assert.deepEqual(platformView({ available: false, channel: 'preview' }), {
    available: false, channel: 'preview', actionLabel: 'Linux Preview unavailable',
  });
});

test('Linux preview view keeps tested environments and the full digest available for copying', () => {
  const linux = { ...windows, channel: 'preview', package_type: 'AppImage', asset_name: 'ROAR-Linux-0.35.2-x86_64.AppImage', tested_environments: ['Ubuntu 24.04'], known_limitations_url: '/linux/' };
  const view = platformView(linux);
  assert.equal(view.checksum, windows.sha256);
  assert.equal(view.checksumLabel, 'ed7180f00bd…4ad768e3');
  assert.deepEqual(view.testedEnvironments, ['Ubuntu 24.04']);
});

test('writeChecksum fails closed when clipboard access is unavailable or rejected', async () => {
  assert.equal(await writeChecksum(undefined, windows.sha256), false);
  assert.equal(await writeChecksum(async () => { throw new Error('denied'); }, windows.sha256), false);
});
