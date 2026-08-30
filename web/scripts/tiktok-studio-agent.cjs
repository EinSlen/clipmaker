#!/usr/bin/env node

const path = require('node:path');

const repositoryRoot = process.env.REPO_ROOT
  ? path.resolve(process.env.REPO_ROOT)
  : path.resolve(__dirname, '..', '..');

require(path.join(repositoryRoot, 'vendor', 'TiktokAutoUploader', 'tiktok_uploader', 'studio-upload.cjs'));
