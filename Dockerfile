FROM node:24-slim AS assets

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY Gruntfile.js .babelrc eslint.config.js ./
COPY static/ static/

RUN cp static/js/custom.js.example static/js/custom.js \
    && cp static/css/custom.css.example static/css/custom.css \
    && pnpm run build


FROM python:3.13-slim AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY merchant/ merchant/
COPY templates/ templates/
COPY static/ static/
COPY runserver.py .

COPY --from=assets /app/static/dist/ static/dist/
COPY --from=assets /app/static/js/custom.js static/js/custom.js
COPY --from=assets /app/static/css/custom.css static/css/custom.css

ENV MERCHANTMAP_HOST=0.0.0.0
EXPOSE 5000

ENTRYPOINT ["python", "runserver.py"]
