FROM python:3.11-slim-bookworm

ENV GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no"

# -----------------------------
# Install system dependencies
# -----------------------------
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    curl wget git procps \
    tesseract-ocr \
    tesseract-ocr-tha \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------
# Install Python libs
# -----------------------------
# ติดตั้ง Docling + FastAPI + dependencies ของคุณทั้งหมด
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir docling --extra-index-url https://download.pytorch.org/whl/cpu

ENV HF_HOME=/tmp/
ENV TORCH_HOME=/tmp/

# -----------------------------
# (Optional) Download Docling models
# -----------------------------
RUN docling-tools models download

# -----------------------------
# Thread tuning (Docling recommendation)
# -----------------------------
ENV OMP_NUM_THREADS=4

# -----------------------------
# Copy FastAPI app
# -----------------------------
WORKDIR /app
COPY . .

# Railway exposes $PORT
ENV PORT=8000

# -----------------------------
# Run FastAPI
# -----------------------------
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
