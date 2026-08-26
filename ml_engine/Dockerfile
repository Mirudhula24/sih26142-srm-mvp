FROM pytorch/pytorch:2.2.2-cuda12.1-cudnn8-runtime

# PyTorch manages its own intra-op threading; pin the other C pools to 1 so GDAL/BLAS
# cannot over-subscribe the CPU alongside it. See docs/TECH_CLASHES.md (Clash 1).
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["celery", "-A", "worker", "worker", "-Q", "inference", "-c", "1", "--loglevel=info"]
