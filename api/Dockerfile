FROM python:3.12-slim
WORKDIR /app
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY api/mordecai ./mordecai
COPY api/tests ./tests
COPY api/pytest.ini ./pytest.ini
COPY blocklists ./blocklists
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 BLOCKLIST_DIR=/app/blocklists
RUN useradd --system --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "mordecai.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
