FROM node:20-alpine

WORKDIR /app

ENV NODE_ENV=production

COPY package*.json ./
RUN npm ci --omit=dev

COPY whatsapp_gateway.js config.js ./

CMD ["node", "whatsapp_gateway.js"]
