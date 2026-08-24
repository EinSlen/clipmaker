import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import test from 'node:test';
import { buildVideoResource, listCredentialAccounts, readCredentialAccounts } from '../../scripts/youtube-data-api-agent.mjs';

test('YouTube OAuth bundles support independent accounts without exposing credentials', () => {
  const bundle = Buffer.from(JSON.stringify({
    accounts: {
      default: { clientId: 'client-one', clientSecret: 'secret-one', refreshToken: 'refresh-one' },
      science_lab: { clientId: 'client-two', clientSecret: 'secret-two', refreshToken: 'refresh-two' },
    },
  }), 'utf8').toString('base64');
  const parsed = readCredentialAccounts(bundle);
  assert.equal(parsed.default.refreshToken, 'refresh-one');
  assert.deepEqual(listCredentialAccounts(bundle), [
    { id: 'default', label: 'Default channel', configured: true },
    { id: 'science_lab', label: 'Science Lab', configured: true },
  ]);
});

test('YouTube Data API metadata is safe, English and deduplicated', () => {
  assert.deepEqual(buildVideoResource({
    title: 'HOW SOFT CAN IT GET? #shorts',
    description: '0% to 100% soft body comparison.',
    tags: ['#softbody', 'softbody', '#simulation'],
    privacy: 'private',
  }), {
    snippet: {
      title: 'HOW SOFT CAN IT GET? #shorts',
      description: '0% to 100% soft body comparison.',
      tags: ['softbody', 'simulation'],
      categoryId: '24',
      defaultLanguage: 'en',
    },
    status: {
      privacyStatus: 'private',
      selfDeclaredMadeForKids: false,
    },
  });
});

test('invalid OAuth bundles are rejected before any network request', () => {
  assert.throws(() => readCredentialAccounts('not-base64-json'), /not a valid credential bundle/u);
});

test('OAuth setup requests offline upload-only access and writes a GitHub secret', async () => {
  const setupPath = new URL('../../scripts/youtube-oauth-setup.mjs', import.meta.url);
  const source = await fs.readFile(setupPath, 'utf8');
  assert.match(source, /https:\/\/www\.googleapis\.com\/auth\/youtube\.upload/u);
  assert.match(source, /access_type: 'offline'/u);
  assert.match(source, /prompt: 'consent'/u);
  assert.match(source, /\['secret', 'set', 'YOUTUBE_OAUTH_ACCOUNTS_B64'/u);
  assert.doesNotMatch(source, /console\.log\([^\n]*(refreshToken|clientSecret)/u);
});
