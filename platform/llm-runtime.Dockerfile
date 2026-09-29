FROM ghcr.io/ggml-org/llama.cpp:server@sha256:8fdfad183be053cdb72d4b6a5930c3a2475730f932855ee9260193422c2564ed

ENV MODEL_ROOT=/models \
    RUNTIME_HOST=0.0.0.0 \
    RUNTIME_PORT=8080 \
    LD_LIBRARY_PATH=/app

WORKDIR /runtime
COPY apps/llm-runtime/supervisor.py /runtime/supervisor.py

EXPOSE 8080
ENTRYPOINT ["python3", "/runtime/supervisor.py"]
