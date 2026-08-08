FROM node:20-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:20-bookworm-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-bookworm-slim AS runtime-base
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
COPY tiktok-upload-requirements.txt /tmp/tiktok-upload-requirements.txt

# ffmpeg + Python + Blender for rendering, Chromium for the uploaders.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      python3 python3-pip python3-venv python3-pil \
      blender \
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
COPY --from=builder /app/data ./data
COPY --from=builder /app/scripts ./scripts
COPY --from=builder /app/next.config.mjs ./next.config.mjs

# Expects a bind mount of the parent repo at /repo (so vendor/ + uploads/ + renders/ persist)
ENV PYTHON_BIN=python3
ENV BLENDER_BIN=blender
EXPOSE 3000
CMD ["npm", "start"]

# Small default runtime used by the long-running application service.
FROM runtime-base AS runtime

# One-shot interactive image used only to create a YouTube browser session on Linux.
FROM runtime-base AS youtube-auth
RUN apt-get update && apt-get install -y --no-install-recommends \
      xvfb x11vnc novnc websockify openbox \
    && rm -rf /var/lib/apt/lists/*
