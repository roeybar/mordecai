FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && apt-get clean
COPY tools/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
RUN useradd -m -u 10001 checker
USER checker
WORKDIR /src
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["sh", "-c", "ruff check --no-cache . && python -m pytest -p no:cacheprovider -q tools/tests"]
