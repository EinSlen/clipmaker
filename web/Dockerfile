FROM node:20-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev=false

FROM node:20-bookworm-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000

# ffmpeg + python + yt-dlp + chromium (for the optional vendor TikTok uploader login)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      python3 python3-pip python3-venv \
      chromium chromium-driver \
      curl ca-certificates fonts-dejavu fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir --break-system-packages yt-dlp

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/data ./data
COPY --from=builder /app/next.config.mjs ./next.config.mjs

# Expects a bind mount of the parent repo at /repo (so vendor/ + uploads/ + renders/ persist)
ENV PYTHON_BIN=python3
EXPOSE 3000
CMD ["npm", "start"]
