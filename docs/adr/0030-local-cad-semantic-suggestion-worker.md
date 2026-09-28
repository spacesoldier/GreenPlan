# ADR-0030 — Локальный worker семантических подсказок для CAD-слоёв

- Status: Accepted
- Date: 2026-09-28
- Owners: ML, backend, CAD domain, data platform
- Related phase: Phase 3, iteration 4
- Supersedes: operational provider wiring of ADR-0023
- Superseded by: —

## Context

Rule provider создаёт воспроизводимые подсказки, но плохо понимает подрядческие сокращения и
неизвестные имена слоёв. Кнопка «Подсказать категории» должна запускать модель в фоне и показывать
отдельные model suggestions. Сейчас `LAYA_URL` поддержан только для классификации роли файла, а
контейнера модели и отдельной очереди семантических задач нет.

Laya предоставляет Jev-compatible `POST /v1/systemone`, Apache-2.0 weights и multilingual
checkpoint. При этом model card прямо предупреждает, что zero-shot accuracy ограничена,
вероятности требуют доменной калибровки, а большое плоское множество вариантов ухудшает качество.

## Decision

1. Добавляется опциональный Compose profile `ai`:
   - `laya` — локальный `laya-serve`, model cache расположен в bind-mounted `data/laya-cache`;
   - `semantic-worker` — Celery consumer очереди `semantic`, обращающийся к Laya по внутренней сети;
   - API только создаёт job и отправляет его в очередь, но не выполняет inference в HTTP request.
2. Laya получает allowlisted `cad-layer-features-v1`: имя слоя, типы и количество entities,
   document role и относительный путь. Геометрия, содержимое файлов и персональные данные не уходят.
3. Категории задаются иерархическим typed-choice вопросом с ограниченным числом coarse labels.
   Provider возвращает confidence и alternatives; ответ проходит schema/taxonomy validation.
4. Model suggestion хранится отдельно от rule suggestion, с provider/model/schema/taxonomy versions,
   input snapshot, probabilities и job identity. Он не меняет effective mapping до review.
5. Ошибка/отсутствие модели переводит job в `failed`, сохраняет диагностическое сообщение и не
   уничтожает rule suggestions. UI не выдаёт rule fallback за нейросетевой ответ.
6. До benchmark на размеченных инженерных решениях используется multilingual checkpoint и статус
   `experimental`. Fine-tuning и temperature calibration выполняются отдельной фазой после
   накопления review corpus.

## Consequences

- модель можно включить локально без передачи проектных материалов наружу;
- тяжёлые weights не входят в обычный запуск и загружаются только профилем `ai`;
- первый cold start может быть долгим и потребует сотен мегабайт диска;
- качество zero-shot не является достаточным основанием для автопринятия;
- API и UI сохраняют работу без AI profile.

## Verification

- API создаёт persisted job и возвращает `202`, не ожидая inference;
- повторный запрос с тем же revision/provider/scope не плодит параллельные jobs;
- worker передаёт только allowlisted feature snapshot;
- invalid provider label отклоняется, job получает terminal error;
- model suggestion не меняет confirmed mapping без engineer review;
- остановленный Laya оставляет rule suggestions доступными;
- UI различает rule/model method, confidence и состояние фоновой операции.

## References

- [ADR-0022](0022-versioned-cad-semantic-taxonomy-and-learning-loop.md)
- [ADR-0023](0023-typed-decision-provider-jev-and-laya.md)
- [Laya model card](https://huggingface.co/convaiinnovations/laya)
- [Phase 3, iteration 4](../dev-plan/phase-03-iteration-04-guided-cad-review.md)
