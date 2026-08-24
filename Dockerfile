FROM python:3.12-slim-bookworm AS runtime

COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/bin/npm /usr/local/bin/npm
COPY --from=node:22-bookworm-slim /usr/local/bin/npx /usr/local/bin/npx
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules

WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PYTHONUNBUFFERED=1

COPY package.json ./
RUN npm install --no-audit --no-fund

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . ./
RUN npm run build \
    && mkdir -p .next/standalone/.next \
    && cp -R public .next/standalone/public \
    && cp -R .next/static .next/standalone/.next/static \
    && cp -R cutscope shots .next/standalone/

WORKDIR /app/.next/standalone
ENV PORT=8080
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
