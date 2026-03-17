FROM node:20-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y wget bzip2 ca-certificates libgl1 libglib2.0-0 libxext6 libxrender1 && \
    rm -rf /var/lib/apt/lists/*

RUN wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh && \
    bash /tmp/miniconda.sh -b -p /opt/conda && \
    rm /tmp/miniconda.sh

ENV PATH="/opt/conda/bin:$PATH"

RUN conda create -n dfm python=3.11 -y

RUN conda install -n dfm -c conda-forge pythonocc-core -y

RUN /opt/conda/envs/dfm/bin/pip install pdfplumber

RUN conda clean -afy

RUN /opt/conda/envs/dfm/bin/python --version

ENV PYTHON_PATH="/opt/conda/envs/dfm/bin/python"

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

RUN npm run build

RUN mkdir -p /app/uploads

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["npm", "start"]

