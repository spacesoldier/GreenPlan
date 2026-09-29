FROM node:22-bookworm-slim AS build

WORKDIR /app
COPY apps/decision-orchestrator/package.json apps/decision-orchestrator/package-lock.json ./
RUN npm ci
COPY apps/decision-orchestrator/tsconfig.json ./
COPY apps/decision-orchestrator/src ./src
RUN npm run build

FROM node:22-bookworm-slim AS runtime

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=8000
WORKDIR /app
COPY apps/decision-orchestrator/package.json apps/decision-orchestrator/package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/dist ./dist

USER node
EXPOSE 8000
CMD ["node", "dist/server.js"]
