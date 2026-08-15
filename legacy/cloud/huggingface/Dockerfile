# Dockerfile pour HuggingFace Spaces (Docker SDK).
# Tout est inclus : Node, ffmpeg, yt-dlp, python.
# Le mode "auto-upload via cookies" (Chromium/Selenium) est volontairement absent — sur HF on utilise
# le flow "Partager → TikTok" depuis le téléphone (Web Share API, HTTPS natif sur *.hf.space).

FROM node:20-bookworm-slim AS deps
WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm install

FROM node:20-bookworm-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY web/ ./
RUN npm run build

FROM node:20-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=7860
ENV HOSTNAME=0.0.0.0
ENV PYTHON_BIN=python3
ENV REPO_ROOT=/repo

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg python3 python3-pip \
      curl ca-certificates fonts-dejavu fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir --break-system-packages yt-dlp \
    && useradd -m -u 1000 user

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.mjs ./next.config.mjs
COPY --from=builder /app/data ./data

# Mutable areas live in /tmp on HF (read-only fs sometimes). We use bind-friendly paths.
RUN mkdir -p uploads renders public/music \
    && chown -R user:user /app

USER user
EXPOSE 7860
CMD ["npx", "next", "start", "-p", "7860", "-H", "0.0.0.0"]
