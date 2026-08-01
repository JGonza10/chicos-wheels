FROM python:3.12-slim

WORKDIR /app

# Las dependencias primero: si no cambian, Docker reutiliza esta capa.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# La base de datos vive en un volumen para sobrevivir a los redespliegues.
# (el volumen se monta en tiempo de ejecución, no aquí: Railway no soporta
# la instrucción VOLUME de Docker, y docker-compose ya declara el suyo)
RUN mkdir -p /app/datos

ENV FLASK_ENV=production \
    PORT=3000 \
    DB_FILE=/app/datos/collecthub.db \
    PYTHONUNBUFFERED=1

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=4s --start-period=8s \
  CMD python -c "import urllib.request,os,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','3000')+'/api/salud').status==200 else 1)"

# Un solo worker: SQLite no admite varios procesos escribiendo el mismo archivo.
# Los hilos sí, y alcanzan de sobra para este caso.
# Forma shell (no exec) para que $PORT se expanda: Railway y hosts similares
# asignan el puerto en tiempo de ejecución, no de build.
CMD gunicorn "collecthub:crear_app()" -b 0.0.0.0:${PORT:-3000} -w 1 --threads 8 --timeout 60
