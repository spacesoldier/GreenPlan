# Локальные модели для CAD-ассистента

Комплект подготовлен для экспериментов из ADR-0032 и ADR-0034. Веса лежат в
`platform/data/llm-models/`, исключены из Git и пока не подключены к постоянно запущенным
контейнерам.

## Состав

| Роль | Репозиторий и ревизия | Файл | Размер |
|---|---|---|---:|
| основной текстовый классификатор | `Qwen/Qwen3-4B-GGUF@bc640142c66e1fdd12af0bd68f40445458f3869b` | `qwen3-4b/Qwen3-4B-Q4_K_M.gguf` | 2 497 280 256 B |
| второе мнение | `ggml-org/gemma-3-4b-it-GGUF@d0976223747697cb51e056d85c532013931fe52e` | `gemma-3-4b-it/gemma-3-4b-it-Q4_K_M.gguf` | 2 489 757 856 B |
| vision projector для будущего разбора легенд и штампов | та же ревизия Gemma | `gemma-3-4b-it/mmproj-model-f16.gguf` | 851 251 104 B |
| более крупный русскоязычный кандидат для benchmark | `yandex/YandexGPT-5-Lite-8B-instruct-GGUF@9fe287d2f512503046bb008aed350f2b4bbb903d` | `yandexgpt-5-lite-8b/YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf` | 4 920 741 184 B |

Суммарный фактический расход каталога — около 11 GiB. Laya остаётся отдельно в
`platform/data/laya-cache/` как действующий baseline.

## Воспроизводимая загрузка

```bash
./platform/scripts/download_llm_models.sh
```

Другой полный путь можно передать первым аргументом:

```bash
./platform/scripts/download_llm_models.sh /mnt/models/greenplan
```

Скрипт продолжает оборванные загрузки, использует закреплённые ревизии, проверяет сигнатуру
`GGUF` и создаёт `SHA256SUMS`. Проверка уже загруженного комплекта:

```bash
cd platform/data/llm-models
sha256sum --check SHA256SUMS
```

## Контрольные суммы текущего комплекта

```text
7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5  qwen3-4b/Qwen3-4B-Q4_K_M.gguf
882e8d2db44dc554fb0ea5077cb7e4bc49e7342a1f0da57901c0802ea21a0863  gemma-3-4b-it/gemma-3-4b-it-Q4_K_M.gguf
8c0fb064b019a6972856aaae2c7e4792858af3ca4561be2dbf649123ba6c40cb  gemma-3-4b-it/mmproj-model-f16.gguf
d9ff5b826f20fbcc2f898f9f2349ac21241579f8fbb79cd32148a333623ba228  yandexgpt-5-lite-8b/YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf
```

## Лицензии

- Qwen3-4B опубликована под Apache-2.0; `LICENSE` сохранён рядом с весами.
- Gemma распространяется по Gemma Terms of Use; условия приведены в официальной карточке модели.
- YandexGPT использует собственную лицензию Yandex; `LICENSE` сохранён рядом с весами.

Перед публикацией сервиса или коммерческой эксплуатацией условия Gemma и YandexGPT надо проверить
отдельно. Само наличие весов не означает разрешение на любой способ распространения.

## Следующий шаг

Не запускать все модели одновременно на конфигурации с 16 GiB RAM. Для реализации ADR-0034 нужен
последовательный `llama.cpp`-runtime: Qwen как основной профиль, Gemma только для второго мнения,
YandexGPT — отдельный benchmark. До подключения к приложению измеряем cold start, peak RSS и tokens/s.

## Запуск runtime и Ax-оркестратора

Сервисы опциональны и находятся в профиле `ai-next`:

```bash
cd platform
docker compose --profile ai-next up -d --build llm-runtime decision-orchestrator
docker compose --profile ai-next ps
```

Healthcheck проверяет веса, но не загружает их в память. Первая модель загружается при первом запросе.
Порты сервисов наружу не публикуются. Диагностический запрос выполняется из Compose-сети:

```bash
docker compose --profile ai-next exec -T decision-orchestrator node -e '
fetch("http://127.0.0.1:8000/v1/decisions/cad-layer", {
  method: "POST",
  headers: {
    "content-type": "application/json",
    "authorization": "Bearer greenplan_local_only"
  },
  body: JSON.stringify({
    featureSnapshot: {
      schema_version: "cad-layer-feature-v1",
      layer_name: "КЛ 0.4кВ",
      entity_types: ["LWPOLYLINE"],
      entity_count: 42
    },
    secondOpinion: false
  })
}).then(async response => {
  console.log(response.status, await response.text());
  if (!response.ok) process.exit(1);
})'
```

Runtime обслуживает только allowlisted aliases и перед сменой профиля выгружает предыдущий
`llama-server`. Остановить сервисы без удаления весов:

```bash
docker compose --profile ai-next stop decision-orchestrator llm-runtime
```
