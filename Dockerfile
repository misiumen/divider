# Hugging Face Space (sdk: docker) / any container host. Serves app.py on port 7860.
FROM python:3.12-slim

# OpenCASCADE and VTK need these shared libraries even headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglu1-mesa libxrender1 libxext6 libx11-6 libxcursor1 libxft2 libxinerama1 libsm6 libice6 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user . .
USER user
ENV HOME=/home/user GRADIO_SERVER_NAME=0.0.0.0
EXPOSE 7860
CMD ["python", "app.py"]
