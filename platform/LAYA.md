# Local semantic suggestion service

Laya is optional and is not started by the ordinary `docker compose up` command. The first start
downloads the multilingual checkpoint into the host directory `platform/data/laya-cache`; allow
approximately 10 GB of free disk for the CPU image, dependencies and cache.

```bash
cd platform
mkdir -p data/laya-cache
docker compose --profile ai up -d --build laya semantic-worker
docker compose --profile ai ps
```

The API creates jobs in the `semantic` Celery queue. Only the semantic worker talks to
`http://laya:8000/v1/systemone`; the Laya port is not published to the host. The default API key is
for the local Compose network only and can be overridden through `LAYA_API_KEY` in an untracked
`.env` file.

Stop the optional services without deleting downloaded weights:

```bash
docker compose --profile ai stop semantic-worker laya
```

Model answers are experimental suggestions. They remain behind engineer review and must not be
used as effective CAD mappings until the two-pilot benchmark and calibration gate are complete.
