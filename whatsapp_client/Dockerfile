FROM node:20-alpine

WORKDIR /app

ENV NODE_ENV=production

COPY package*.json ./
RUN npm ci --omit=dev

COPY bot.mjs config.js ./

CMD ["node", "bot.mjs"]
