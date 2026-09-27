FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=180

WORKDIR /app

COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN python -c "import tomllib; print(chr(10).join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" \
      > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt

COPY apps/api/src ./src
RUN pip install --no-cache-dir --no-deps .

RUN useradd --create-home --uid 10001 greenplan
USER greenplan

EXPOSE 8000
CMD ["uvicorn", "greenplan_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
