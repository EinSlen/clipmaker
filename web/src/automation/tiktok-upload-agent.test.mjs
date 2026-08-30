import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const { parseReceipt, parseFailure } = require('../../scripts/tiktok-upload-agent.cjs');

const prefix = 'CLIPMAKER_RECEIPT:';
const username = 'dvlad';
const postId = '7679769560043605270';
const releaseUrl = `https://www.tiktok.com/@${username}/video/${postId}`;

function output(receipt) {
  return `diagnostic\n${prefix}${JSON.stringify(receipt)}\n`;
}

test('the historical TikTok API receipt remains the primary accepted proof', () => {
  const receipt = parseReceipt(output({
    provider: 'tiktok-web-upload',
    platformPostId: postId,
    releaseUrl,
    raw: {
      privacy: 'private', statusCode: 0, creationId: '123456789012345678901', uploadVideoId: postId,
    },
  }), username);
  assert.equal(receipt?.provider, 'tiktok-web-upload');
  assert.equal(receipt?.platformPostId, postId);
});

test('Studio receipts and ambiguous API recoveries require visible post evidence', () => {
  for (const provider of ['tiktok-studio-browser', 'tiktok-web-upload']) {
    const receipt = parseReceipt(output({
      provider,
      platformPostId: postId,
      releaseUrl,
      raw: {
        privacy: 'private', statusCode: 0, evidence: 'studio-content', verifiedInStudio: true, account: username,
      },
    }), username);
    assert.equal(receipt?.provider, provider);
  }
  assert.equal(parseReceipt(output({
    provider: 'tiktok-studio-browser', platformPostId: postId, releaseUrl,
    raw: { privacy: 'private', statusCode: 0 },
  }), username), null);
});

test('forged URLs, account mismatches and non-post identifiers are rejected', () => {
  const base = {
    provider: 'tiktok-web-upload', platformPostId: postId, releaseUrl,
    raw: { privacy: 'private', statusCode: 0, creationId: 'creation', uploadVideoId: postId },
  };
  assert.equal(parseReceipt(output({ ...base, releaseUrl: 'https://example.com/fake' }), username), null);
  assert.equal(parseReceipt(output({ ...base, platformPostId: 'not-a-post' }), username), null);
  assert.equal(parseReceipt(output({ ...base, raw: { ...base.raw, statusCode: 1 } }), username), null);
});

test('Studio fallback is allowed only before the final API commit request', () => {
  const safe = parseFailure(`CLIPMAKER_FAILURE:${JSON.stringify({
    provider: 'tiktok-web-upload', stage: 'media-upload', commitAttempted: false, safeToFallback: true,
  })}`);
  const ambiguous = parseFailure(`CLIPMAKER_FAILURE:${JSON.stringify({
    provider: 'tiktok-web-upload', stage: 'commit-request', commitAttempted: true, safeToFallback: false,
  })}`);
  assert.equal(safe?.safeToFallback, true);
  assert.equal(ambiguous?.safeToFallback, false);
  assert.equal(ambiguous?.commitAttempted, true);
});
