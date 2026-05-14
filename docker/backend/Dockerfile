# FastAPI backend image for HydroCalc (v0.2.0+).
#
# Mirrors the conda-based build used by the legacy Flask service in
# docker/main/Dockerfile, but boots uvicorn against backend.main:app.
# Once the migration completes (end of Phase 3) the legacy image will
# be deleted.

FROM continuumio/miniconda3:latest

WORKDIR /hydro

# Cache deps separately from app code so source edits don't bust the layer.
COPY requirements-conda.txt requirements-pip.txt ./

RUN conda config --set solver libmamba

# System deps required by psycopg2 build (kept matching the legacy image to
# avoid surprises in the conda environment).
RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql-client \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN conda install -y -c conda-forge python=3.11.10
RUN conda config --set solver classic
RUN conda install -y -c conda-forge --file requirements-conda.txt
RUN pip install --no-cache-dir -r requirements-pip.txt

ENV PROJ_LIB=/opt/conda/share/proj \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/hydro

# Copy only the new layout. Legacy /app and /scripts are mounted at runtime
# during the migration so the legacy Flask service can share the source tree.
COPY backend/ /hydro/backend
COPY data/datasets.lock.json /hydro/data/datasets.lock.json
COPY docs/ /hydro/docs

EXPOSE 8000

# --proxy-headers so we can deploy behind a reverse proxy later (Phase 6).
CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers"]
