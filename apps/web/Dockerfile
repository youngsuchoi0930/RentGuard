FROM node:22-alpine AS dependencies
RUN corepack enable
WORKDIR /app
COPY package.json ./
RUN pnpm install --frozen-lockfile=false

FROM node:22-alpine AS builder
RUN corepack enable
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app .
EXPOSE 3000
CMD ["npm", "run", "start"]
