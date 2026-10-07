# Playwright runner, pinned to the same version as the npm dep so the
# bundled browsers match. Self-contained: the suite drives the api over
# the compose network (BASE_URL=http://web:8080), it is not part of the
# served stack (profiles: [tools]).
FROM mcr.microsoft.com/playwright:v1.48.0-jammy

WORKDIR /e2e

COPY package.json ./
RUN npm install --no-audit --no-fund

COPY playwright.config.ts ./
COPY tests/ ./tests/

# Report lands here; bind-mounted to ./e2e/report on the host so the
# HTML report can be opened after a run.
RUN mkdir -p /e2e/report

ENV CI=1
CMD ["npx", "playwright", "test"]
