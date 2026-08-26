FROM python:3.10-slim

# Lock C-library thread pools to a single thread. GDAL, OpenCV and NumPy/BLAS each
# spawn their own OpenMP pool; left at defaults they over-subscribe the CPU and stall
# the ingestion worker. See docs/TECH_CLASHES.md (Clash 1).
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      gdal-bin libgdal-dev build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
