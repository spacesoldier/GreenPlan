FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 \
    USE_TF=0 \
    HF_HOME=/models/huggingface \
    LAYA_HOST=0.0.0.0 \
    LAYA_PORT=8000

RUN pip install "laya[serve]==0.3.20"

EXPOSE 8000
CMD ["laya-serve"]
