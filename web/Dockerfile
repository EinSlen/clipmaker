FROM node:20-bookworm-slim AS deps
WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm ci

FROM node:20-bookworm-slim AS tiktok-signature-deps
WORKDIR /tiktok-signature
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
COPY vendor/TiktokAutoUploader/tiktok_uploader/tiktok-signature/package.json \
     vendor/TiktokAutoUploader/tiktok_uploader/tiktok-signature/package-lock.json ./
RUN npm ci --omit=dev

FROM node:20-bookworm-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY web/ .
RUN npm run build

FROM node:20-bookworm-slim AS runtime-base
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
COPY web/tiktok-upload-requirements.txt /tmp/tiktok-upload-requirements.txt

# ffmpeg + Python + Blender for rendering, Chromium for the uploaders.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      python3 python3-pip python3-venv python3-pil \
      blender \
      gh \
      chromium chromium-driver \
      curl ca-certificates fonts-dejavu fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir --break-system-packages yt-dlp -r /tmp/tiktok-upload-requirements.txt \
    && rm -f /tmp/tiktok-upload-requirements.txt

# Blender headless needs EGL even when it falls back to software rendering.
RUN apt-get update && apt-get install -y --no-install-recommends libegl1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/src ./src
COPY --from=builder /app/config ./config
COPY --from=builder /app/data ./data
COPY --from=builder /app/scripts ./scripts
COPY --from=builder /app/next.config.mjs ./next.config.mjs
COPY --from=tiktok-signature-deps /tiktok-signature/node_modules /opt/tiktok-signature/node_modules

# Expects a bind mount of the parent repo at /repo (so vendor/ + uploads/ + renders/ persist)
ENV PYTHON_BIN=python3
ENV BLENDER_BIN=blender
ENV NODE_PATH=/opt/tiktok-signature/node_modules
EXPOSE 3000
CMD ["npm", "start"]

# Small default runtime used by the long-running application service.
FROM runtime-base AS runtime

# Reproducible GitHub Actions image. It keeps the complete source tree and
# development dependencies so the cloud runner tests the same Blender/FFmpeg
# stack as production without installing tools directly on the host runner.
FROM runtime-base AS ci
ENV NODE_ENV=test
RUN apt-get update && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*
# runtime-base already contains the built application, source, scripts and
# node_modules. TypeScript only needs the project configuration files omitted
# from the lean runtime image.
COPY --from=builder /app/tsconfig.json ./tsconfig.json
COPY --from=builder /app/next-env.d.ts ./next-env.d.ts
COPY --from=builder /app/postcss.config.js ./postcss.config.js
COPY --from=builder /app/tailwind.config.ts ./tailwind.config.ts
CMD ["npm", "test"]

# One-shot interactive image used only to create a YouTube browser session on Linux.
FROM runtime-base AS youtube-auth
RUN apt-get update && apt-get install -y --no-install-recommends \
      xvfb x11vnc novnc websockify openbox \
    && rm -rf /var/lib/apt/lists/*
