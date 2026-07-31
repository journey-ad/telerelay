FROM node:22-alpine AS frontend-builder
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY frontend/package.json ./frontend/package.json
RUN pnpm install --frozen-lockfile --filter ./frontend
COPY frontend/ ./frontend/
RUN pnpm --dir frontend build

FROM python:3.11-slim AS python-builder
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
RUN mkdir -p /app/logs /app/data /app/config
COPY --from=python-builder /root/.local /root/.local
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/root/.local/bin:$PATH
COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
COPY config/*.example ./config/
ARG GIT_SHA=""
RUN echo "${GIT_SHA}" > ./backend/.commit
EXPOSE 8080
CMD ["python", "-m", "backend.main"]
