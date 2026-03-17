# ── Stage 1: Node app ──
FROM node:20-slim AS base

WORKDIR /app

# Install system deps for conda
RUN apt-get update && apt-get install -y wget bzip2 ca-certificates libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

# Install miniconda
RUN wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh && \
    bash /tmp/miniconda.sh -b -p /opt/conda && \
    rm /tmp/miniconda.sh

ENV PATH="/opt/conda/bin:$PATH"

# Create conda env with pythonocc-core
RUN conda create -n dfm python=3.11 -y && \
    conda install -n dfm -c conda-forge pythonocc-core -y && \
    conda run -n dfm pip install pdfplumber && \
    conda clean -afy

# Set PYTHON_PATH for the app
ENV PYTHON_PATH="/opt/conda/envs/dfm/bin/python"

# Install Node dependencies
COPY package.json package-lock.json* ./
RUN npm ci

# Copy all source code
COPY . .

# Build Next.js
RUN npm run build

# Create uploads directory
RUN mkdir -p /app/uploads

# Expose port
EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Start
CMD ["npm", "start"]