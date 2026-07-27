# Local prototype image: runs the Vite dev server so the Compose stack stays
# fast to iterate on. A production static build is out of scope until
# Milestone 8 packaging per HANDOFF.md.
FROM node:22.23.1-alpine3.24

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
