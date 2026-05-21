FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --gid 1000 hellomate \
    && useradd --uid 1000 --gid hellomate --create-home --shell /usr/sbin/nologin hellomate

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data \
    && chown -R hellomate:hellomate /app

USER hellomate

CMD ["python", "-m", "app.main"]
