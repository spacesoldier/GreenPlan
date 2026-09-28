# Phase 3, iteration 4 — checkpoint 1

- Status: Verified vertical slice; model runtime pending
- Date: 2026-09-28
- Decisions: ADR-0029, ADR-0030

## Delivered

- этапы подготовки вынесены в верхний мастер с конечной целью публикации;
- CAD-граф перенесён в левую панель и содержит документы, Model/Paper spaces, слои и XREF;
- document/space/layer/XREF selection управляет центральным inspector;
- пространства документа работают как вкладки; ограничение отсутствующих per-viewport layer states
  подписано непосредственно в UI;
- bottom tray содержит вкладки «Проблемы» и «Журнал», складывается и меняет высоту pointer drag;
- высота tray ограничена безопасным диапазоном и сохраняется в browser storage;
- добавлены persisted semantic jobs, API start/status, очередь `semantic`, worker adapter и
  отдельные model suggestions с provenance;
- Compose profile `ai` содержит `laya` и `semantic-worker`, а model cache bind-mounted в
  `platform/data/laya-cache`;
- если профиль модели не запущен, кнопка получает быстрый диагностический `503`, не создавая
  зависшую задачу и не маскируя rule result под нейросетевой.

## Evidence

- frontend: 8 suites, 45 tests; TypeScript check и production Next.js build проходят;
- backend: 29 targeted tests и Python compileall проходят;
- migration `014_semantic_suggestion_jobs.sql` применена к локальному PostGIS;
- обычные API/web containers пересобраны; API healthy;
- экран «Старый Гай» проверен headless screenshot при 1600×1100;
- `docker compose --profile ai config --services` включает `laya` и `semantic-worker`;
- model-unavailable contract фактически возвращает `503 semantic_provider_unavailable`.

## Runtime gate

AI profile намеренно не запущен на этой машине. На момент проверки домашний раздел имеет только
16 ГБ свободного места при заполнении 97%. Официальная инструкция Laya рекомендует для CPU
quickstart 8 ГБ RAM и 10 ГБ свободного диска; скачивание образа и checkpoint оставило бы слишком
малый эксплуатационный резерв.

Перед первым запуском нужно освободить дополнительное место либо перенести
`platform/data/laya-cache` на отдельный диск через bind mount. После этого выполнить инструкцию
[platform/LAYA.md](../../platform/LAYA.md) и перейти к benchmark gate на двух пилотах.
