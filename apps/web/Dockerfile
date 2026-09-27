FROM node:24-alpine AS dependencies
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM dependencies AS builder
WORKDIR /app
COPY apps/web/ ./
RUN npm run build

FROM node:24-alpine AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app
RUN addgroup -S --gid 10001 greenplan && adduser -S --uid 10001 -G greenplan greenplan
COPY --from=builder --chown=greenplan:greenplan /app/public ./public
COPY --from=builder --chown=greenplan:greenplan /app/.next/standalone ./
COPY --from=builder --chown=greenplan:greenplan /app/.next/static ./.next/static
USER greenplan
EXPOSE 3000
CMD ["node", "server.js"]
