# CAD Docker adapters

## LibreDWG: диагностика вторым reader

LibreDWG — GPL-3.0-or-later. Этот образ предназначен для чтения и диагностики, а не для гарантированного production-экспорта DXF. Он собирается из закреплённого исходника GNU с проверкой SHA-256; сборка намеренно ограничена двумя параллельными задачами, чтобы не перегружать рабочую машину.

```bash
docker build -f docker/libredwg/Dockerfile -t greenplan/libredwg:0.14 .

docker run --rm \
  -v "$PWD/dataset:/data:ro" \
  -v "$PWD/reports/libredwg:/out" \
  greenplan/libredwg:0.14 \
  -v1 -O JSON -o /out/pilot.json \
  '/data/path/to/pilot.dwg' \
  2>/out/pilot.stderr
```

Использование: сравнить факт чтения, stderr, JSON/GeoJSON, список слоёв и типы объектов с результатом ODA. Не использовать LibreDWG для обратной записи DWG R2004+ или как единственный источник истины: его документация прямо помечает часть современных объектов и DXF-экспорт как незрелые.

## ODA: частный адаптер без redistribution

ODA File Converter полезен как основной DWG→DXF-адаптер для хакатонного non-commercial контура. В этот репозиторий и базовый образ **не включается** ODA DEB/AppImage/SDK. Получите пакет сами, примите его условия и распакуйте приложение локально:

```bash
mkdir -p /tmp/oda-app
dpkg-deb -x /path/to/ODAFileConverter.deb /tmp/oda-app
```

Сборка адаптера:

```bash
docker build -f docker/oda-adapter/Dockerfile -t greenplan/oda-adapter:local .
```

Запуск на папке проекта:

```bash
docker run --rm \
  -v /tmp/oda-app/usr/bin/ODAFileConverter_27.1.0.0:/opt/oda:ro \
  -e ODA_BIN=/opt/oda/ODAFileConverter \
  -v "$PWD/dataset/Пилотный проект 20 улиц/2. Песчаный переулок/Проектное решение /DWG:/input:ro" \
  -v "$PWD/artifacts/oda-output:/output" \
  -e ODA_TIMEOUT=900 \
  greenplan/oda-adapter:local /input /output 1 1 '*.dwg'
```

Контейнер монтирует вход read-only, пишет только в `/output`, запускает ODA через `xvfb-run`, передаёт ему фиксированный выход `ACAD2018 DXF` и аварийно завершает зависшую задачу по `ODA_TIMEOUT`. В адаптер намеренно включены только открытые системные GUI-зависимости ODA (включая виртуальный дисплей); сам ODA не включён. Лог контейнера — часть протокола импорта. Для будущей коммерческой/заказной поставки нужен отдельный юридически подтверждённый способ лицензирования и поставки ODA SDK; mount-схема не выдаётся за self-contained delivery.
