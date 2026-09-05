import assert from 'node:assert/strict';
import test from 'node:test';
import { validateAiRequest } from '../src/index.js';

test('a video request is pinned to a vertical frame and a bounded length', () => {
  const request = validateAiRequest({ task: 'video', input: { prompt: 'a cracked porcelain mask', duration: 10, seed: 42 } });
  assert.equal(request.model, 'alibaba/hh1.1-t2v');

  // A landscape clip would reach the shorts feed cropped, so the runner is
  // never allowed to choose the frame.
  assert.equal(request.input.ratio, '9:16');
  assert.equal(request.input.watermark, false);
  assert.equal(request.input.duration, 10);
  assert.equal(request.input.seed, 42);

  // Duration drives the Neuron bill, and the model itself refuses anything
  // outside three to fifteen seconds.
  assert.equal(validateAiRequest({ task: 'video', input: { prompt: 'x', duration: 90 } }).input.duration, 15);
  assert.equal(validateAiRequest({ task: 'video', input: { prompt: 'x', duration: 1 } }).input.duration, 3);
  assert.equal(validateAiRequest({ task: 'video', input: { prompt: 'x' } }).input.duration, 10);

  // An unseeded request stays unseeded rather than being pinned to zero, which
  // would make every episode of the series open on the same frame.
  assert.equal(Object.hasOwn(validateAiRequest({ task: 'video', input: { prompt: 'x' } }).input, 'seed'), false);

  assert.equal(validateAiRequest({ task: 'video', input: { prompt: 'x', resolution: '720P' } }).input.resolution, '720P');
  assert.equal(validateAiRequest({ task: 'video', input: { prompt: 'x', resolution: '4K' } }).input.resolution, '1080P');
  assert.throws(() => validateAiRequest({ task: 'video', input: { prompt: '' } }), /Prompt de vidéo invalide/);
  assert.throws(() => validateAiRequest({ task: 'video', input: { prompt: 'x'.repeat(2501) } }), /Prompt de vidéo invalide/);
});

test('only the five story tasks are reachable', () => {
  assert.throws(() => validateAiRequest({ task: 'embeddings', input: {} }), /Tâche IA inconnue/);
  assert.throws(() => validateAiRequest({ task: '', input: {} }), /Tâche IA inconnue/);
  assert.throws(() => validateAiRequest({ task: 'image' }), /Entrée IA manquante/);
});

test('an image request is pinned to flux and drops the properties the model rejects', () => {
  const request = validateAiRequest({ task: 'image', input: { prompt: 'une fraise à lunettes', steps: 40, seed: 7 } });
  assert.equal(request.model, '@cf/black-forest-labs/flux-1-schnell');
  assert.deepEqual(Object.keys(request.input).sort(), ['prompt', 'steps']);
  assert.equal(request.input.steps, 8);
  assert.throws(() => validateAiRequest({ task: 'image', input: { prompt: '' } }), /Prompt d’image invalide/);
});

test('speech is English only and rejects unknown speakers', () => {
  const request = validateAiRequest({ task: 'speech', input: { prompt: 'hello there', speaker: 'vesta' } });
  assert.equal(request.model, '@cf/deepgram/aura-2-en');
  assert.equal(request.input.text, 'hello there');
  assert.equal(request.input.encoding, 'mp3');
  assert.throws(() => validateAiRequest({ task: 'speech', input: { prompt: 'hi', speaker: 'bob' } }), /Voix invalide/);
});

test('a text request caps the conversation and the sampling parameters', () => {
  const request = validateAiRequest({
    task: 'text',
    input: {
      messages: [{ role: 'system', content: 'tu écris' }, { role: 'user', content: 'écris' }],
      max_tokens: 99_999,
      temperature: 9,
      json: true,
    },
  });
  assert.equal(request.model, '@cf/meta/llama-3.3-70b-instruct-fp8-fast');
  assert.equal(request.input.max_tokens, 4096);
  assert.equal(request.input.temperature, 2);
  assert.deepEqual(request.input.response_format, { type: 'json_object' });

  assert.throws(() => validateAiRequest({ task: 'text', input: { messages: [] } }), /Conversation invalide/);
  assert.throws(() => validateAiRequest({
    task: 'text',
    input: { messages: [{ role: 'root', content: 'x' }] },
  }), /Rôle invalide/);
  assert.throws(() => validateAiRequest({
    task: 'text',
    input: { messages: [{ role: 'user', content: 'x'.repeat(24_001) }] },
  }), /Conversation trop longue/);
});

test('transcription accepts base64 audio within the body limit and pins the language', () => {
  const audio = Buffer.from('x'.repeat(4096)).toString('base64');
  const request = validateAiRequest({ task: 'transcribe', input: { audio, language: 'fr' } });
  assert.equal(request.model, '@cf/openai/whisper-large-v3-turbo');
  assert.equal(request.input.audio, audio);
  assert.equal(request.input.language, 'fr');
  assert.equal(request.input.task, 'transcribe');

  assert.throws(() => validateAiRequest({ task: 'transcribe', input: { audio: '' } }), /Audio à transcrire invalide/);
  assert.throws(() => validateAiRequest({
    task: 'transcribe',
    input: { audio: 'a'.repeat(90_001) },
  }), /Audio à transcrire invalide/);
  assert.throws(() => validateAiRequest({
    task: 'transcribe',
    input: { audio: 'not base64 !!' },
  }), /Audio à transcrire mal encodé/);
  assert.throws(() => validateAiRequest({
    task: 'transcribe',
    input: { audio, language: 'francais' },
  }), /Langue invalide/);
});
