# ADR-0033 — Дедуплицированное хранилище свидетельств и векторный retrieval

- Status: Proposed
- Date: 2026-09-28
- Owners: data platform, ML, CAD domain, regulatory domain
- Related: ADR-0003, ADR-0006, ADR-0022, ADR-0032

## Context

Системе нужны два связанных, но разных корпуса:

1. инженерные примеры CAD-слоёв, их признаки, предложенные и подтверждённые категории;
2. нормативные документы, редакции, разделы, таблицы и фрагменты, на которые должны ссылаться правила.

LLM не должна получать весь корпус в prompt. Ей нужен retrieval релевантных примеров и нормативных
фрагментов. При повторных загрузках проектов, XREF и редакций документов одни и те же материалы могут
появляться много раз. Векторная близость полезна для поиска, но недостаточно надёжна для идентичности и
дедупликации.

В проекте уже работает PostgreSQL/PostGIS. Проверка текущего образа `postgis/postgis:16-3.5-alpine`
показала, что расширение `vector` в нём сейчас отсутствует. Добавление pgvector потребует собственного
воспроизводимого образа и миграции.

## Decision

### 1. PostgreSQL остаётся источником истины

Документы, редакции, chunks, CAD observations, review events, provenance и связи хранятся в Postgres.
Векторный индекс является производной проекцией: его можно полностью перестроить из исходных записей.
Удаление или повреждение индекса не должно уничтожать доказательства и инженерные решения.

### 2. Дедупликация многоступенчатая

Идентичность не определяется расстоянием между embeddings.

- байтовый дубль: SHA-256 исходного файла;
- текстовый дубль: SHA-256 канонизированного текста с сохранением ссылки на каждый источник;
- дубль нормативного chunk: `document_revision + structural_path + canonical_text_hash`;
- дубль CAD-примера: версия extractor-а, нормализованное имя, entity signature и контекстная область;
- near-duplicate: только кандидат, найденный embedding/лексическим поиском; слияние выполняется
  детерминированным правилом либо после review.

Несколько источников могут ссылаться на один canonical content object. Provenance не удаляется при
дедупликации.

### 3. Корпуса логически разделены

`cad_exemplars` и `regulation_chunks` используют общую инфраструктуру embedding jobs, но разные схемы
chunking, фильтры, пороги и evaluation datasets. Запрос классификатора слоя не должен случайно получать
нормативный абзац, а нормативный RAG — подрядческое имя слоя без явного cross-corpus запроса.

Для нормативов сохраняются документ, редакция, статус действия, страница, заголовочный путь, координаты
фрагмента на странице, текст и таблицы. Ответ LLM обязан ссылаться на конкретные chunks; найденный текст
остаётся свидетельством, а исполняемым правилом становится только утверждённая нормализованная норма.

### 4. Начальный backend — pgvector в собственном PostGIS-образе

Для текущего масштаба выбирается pgvector:

- транзакционные metadata, ACL, версии и embeddings остаются рядом;
- проще обеспечить согласованное удаление, дедупликацию и аудит;
- доступны exact search, HNSW/IVFFlat и hybrid search совместно с PostgreSQL full-text search;
- отдельный сервис, протокол синхронизации и второй backup пока не требуются.

Создаётся производный образ, основанный на закреплённой версии PostGIS и pgvector. Миграция включает
`CREATE EXTENSION vector`; до успешного smoke-test текущий контейнер БД не заменяется.

Qdrant остаётся поддерживаемой реализацией `RetrievalIndex`, но не источником истины. Переход к нему
рассматривается, если корпус вырастет до миллионов chunks, потребуется отдельное масштабирование поиска,
несколько dense/sparse/multivector представлений или pgvector не выполнит измеренные latency/recall SLO.
Qdrant умеет named dense/sparse vectors, payload filters и hybrid/multistage queries, но потребует
outbox-синхронизации и отдельной процедуры snapshots.

### 5. Поиск гибридный

Для аббревиатур, кодов норм и обозначений слоёв точное совпадение особенно важно. Candidate retrieval
объединяет:

- полнотекстовый/лексический поиск;
- dense embedding similarity;
- структурные фильтры: corpus, taxonomy/document revision, contractor, project, file role;
- optional reranker над небольшим top-k.

Результаты объединяются RRF либо другой стратегией, выбранной на размеченном evaluation set. Порог
сходства нельзя назначать без измерений отдельно для CAD и нормативов.

### 6. Embedding-модель отделена от LLM

Embeddings создаёт небольшой CPU encoder, а генеративная LLM получает только найденные фрагменты.
Каждая запись содержит `embedding_model`, revision, dimensions, normalization и input hash. Смена модели
создаёт новое embedding-представление и фоновый reindex, не перезаписывая старое.

Первый benchmark сравнивает `multilingual-e5-small` как дешёвый baseline с одной более сильной
многоязычной моделью. Генеративные Qwen/Gemma/YandexGPT не используются для массового построения
embeddings.

## Data outline

- `evidence_content(id, canonical_hash, media_kind, canonical_text, created_at)`;
- `evidence_source(id, content_id, asset_id/document_revision_id, locator, provenance)`;
- `evidence_chunk(id, content_id, corpus, structural_path, page_no, text_hash, text)`;
- `cad_exemplar(id, observation_id, confirmed_mapping_id, signature_hash, scope)`;
- `embedding_record(id, subject_type, subject_id, model_revision, input_hash, dimensions, vector)`;
- `retrieval_evaluation(id, corpus, query_set_version, backend, model_revision, metrics)`.

Unique constraints обеспечивают exact dedup. Outbox понадобится только при внешнем индексе вроде Qdrant.

## Resource envelope

На минимальной машине из ТЗ — 16 ГБ RAM — одновременно резервируется память для ОС, Postgres,
API/workers и CAD-конвертации. Поэтому vector index должен уметь работать с ограниченным cache, а
embedding/LLM jobs выполняются очередью с concurrency 1. Тяжёлый CAD-анализ и LLM inference не запускаются
параллельно без измерения peak RSS.

## Verification

- повторная загрузка того же файла создаёт новый provenance, но не дублирует canonical content;
- повторная индексация той же model revision идемпотентна;
- near-duplicate не сливается автоматически только по cosine distance;
- поиск нормативов возвращает страницу и структурный путь каждого фрагмента;
- удаление vector projection не мешает восстановить её из Postgres;
- lexical, dense и hybrid retrieval сравниваются на размеченных запросах;
- benchmark включает recall@k, nDCG@k, latency p95, размер индекса и peak RSS;
- полный профиль приложения укладывается в 16 ГБ либо явно маркируется как профиль для 32 ГБ.

## References

- [pgvector](https://github.com/pgvector/pgvector)
- [Qdrant hybrid queries](https://qdrant.tech/documentation/search/hybrid-queries/)
- [Qdrant payload filtering](https://qdrant.tech/documentation/search/filtering/)
- [Qdrant snapshots](https://qdrant.tech/documentation/operations/snapshots/)
- [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small)
- [ADR-0006](0006-regulatory-documents-and-executable-rules.md)
- [ADR-0032](0032-evidence-assisted-cad-layer-semantics.md)
