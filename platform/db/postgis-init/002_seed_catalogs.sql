\set ON_ERROR_STOP on

BEGIN;

INSERT INTO biology.growth_stages(id, code, title, ordinal) VALUES
  ('10000000-0000-0000-0000-000000000001', 'at_planting', 'При посадке', 1),
  ('10000000-0000-0000-0000-000000000002', 'design_horizon', 'Расчётный горизонт', 2),
  ('10000000-0000-0000-0000-000000000003', 'mature', 'Зрелое растение', 3)
ON CONFLICT (code) DO NOTHING;

INSERT INTO biology.requirement_definitions(id, code, title, value_kind, canonical_unit, safety_critical) VALUES
  ('11000000-0000-0000-0000-000000000001', 'crown_clearance', 'Свободное пространство для кроны', 'numeric', 'm', true),
  ('11000000-0000-0000-0000-000000000002', 'rootable_area', 'Непрерывная корнеобитаемая площадь', 'numeric', 'm2', true),
  ('11000000-0000-0000-0000-000000000003', 'rootable_depth', 'Эффективная глубина грунта', 'numeric', 'm', true),
  ('11000000-0000-0000-0000-000000000004', 'rootable_volume', 'Корнеобитаемый объём', 'numeric', 'm3', true),
  ('11000000-0000-0000-0000-000000000005', 'open_soil_area', 'Открытая площадь почвы', 'numeric', 'm2', true),
  ('11000000-0000-0000-0000-000000000006', 'soil_ph', 'Кислотность почвы', 'numeric', 'pH', false),
  ('11000000-0000-0000-0000-000000000007', 'soil_texture', 'Механический состав почвы', 'category', NULL, false),
  ('11000000-0000-0000-0000-000000000008', 'drainage', 'Дренируемость', 'category', NULL, true),
  ('11000000-0000-0000-0000-000000000009', 'light', 'Освещённость', 'category', NULL, false),
  ('11000000-0000-0000-0000-000000000010', 'irrigation', 'Обеспечение поливом', 'category', NULL, false)
ON CONFLICT (code) DO NOTHING;

INSERT INTO geo.object_classes(id, code, path, parent_id, title, is_constraint_source) VALUES
  ('20000000-0000-0000-0000-000000000001', 'territory', 'territory', NULL, 'Территория', false),
  ('20000000-0000-0000-0000-000000000002', 'structure', 'structure', NULL, 'Сооружение', true),
  ('20000000-0000-0000-0000-000000000003', 'transport', 'transport', NULL, 'Транспортная инфраструктура', true),
  ('20000000-0000-0000-0000-000000000004', 'utility', 'utility', NULL, 'Инженерная сеть', true),
  ('20000000-0000-0000-0000-000000000005', 'vegetation', 'vegetation', NULL, 'Растительность', true),
  ('20000000-0000-0000-0000-000000000006', 'surface', 'surface', NULL, 'Покрытие', true),
  ('20000000-0000-0000-0000-000000000007', 'annotation', 'annotation', NULL, 'Аннотация', false),
  ('20000000-0000-0000-0000-000000000008', 'unknown', 'unknown', NULL, 'Неопознанный объект', true)
ON CONFLICT (code) DO NOTHING;

INSERT INTO geo.object_classes(id, code, path, parent_id, title, is_constraint_source) VALUES
  ('21000000-0000-0000-0000-000000000001', 'territory.work_boundary', 'territory.work_boundary', '20000000-0000-0000-0000-000000000001', 'Граница работ', false),
  ('21000000-0000-0000-0000-000000000002', 'structure.building', 'structure.building', '20000000-0000-0000-0000-000000000002', 'Здание', true),
  ('21000000-0000-0000-0000-000000000003', 'transport.road', 'transport.road', '20000000-0000-0000-0000-000000000003', 'Дорога', true),
  ('21000000-0000-0000-0000-000000000004', 'utility.water', 'utility.water', '20000000-0000-0000-0000-000000000004', 'Водоснабжение', true),
  ('21000000-0000-0000-0000-000000000005', 'utility.gas', 'utility.gas', '20000000-0000-0000-0000-000000000004', 'Газоснабжение', true),
  ('21000000-0000-0000-0000-000000000006', 'utility.power', 'utility.power', '20000000-0000-0000-0000-000000000004', 'Электроснабжение', true),
  ('21000000-0000-0000-0000-000000000007', 'utility.sewer', 'utility.sewer', '20000000-0000-0000-0000-000000000004', 'Канализация', true),
  ('21000000-0000-0000-0000-000000000008', 'utility.telecom', 'utility.telecom', '20000000-0000-0000-0000-000000000004', 'Связь', true),
  ('21000000-0000-0000-0000-000000000009', 'vegetation.existing', 'vegetation.existing', '20000000-0000-0000-0000-000000000005', 'Существующая растительность', true),
  ('21000000-0000-0000-0000-000000000010', 'vegetation.proposed', 'vegetation.proposed', '20000000-0000-0000-0000-000000000005', 'Проектируемая растительность', true),
  ('21000000-0000-0000-0000-000000000011', 'surface.lawn', 'surface.lawn', '20000000-0000-0000-0000-000000000006', 'Газон', false),
  ('21000000-0000-0000-0000-000000000012', 'annotation.sheet_frame', 'annotation.sheet_frame', '20000000-0000-0000-0000-000000000007', 'Рамка листа', false),
  ('21000000-0000-0000-0000-000000000013', 'unknown.constraint', 'unknown.constraint', '20000000-0000-0000-0000-000000000008', 'Неопознанное ограничение', true)
ON CONFLICT (code) DO NOTHING;

INSERT INTO geo.object_classes(id, code, path, parent_id, title, is_constraint_source) VALUES
  ('22000000-0000-0000-0000-000000000001', 'transport.road.carriageway', 'transport.road.carriageway', '21000000-0000-0000-0000-000000000003', 'Проезжая часть', true),
  ('22000000-0000-0000-0000-000000000002', 'transport.road.curb', 'transport.road.curb', '21000000-0000-0000-0000-000000000003', 'Бортовой камень', true),
  ('22000000-0000-0000-0000-000000000003', 'utility.water.pipeline', 'utility.water.pipeline', '21000000-0000-0000-0000-000000000004', 'Водопровод', true),
  ('22000000-0000-0000-0000-000000000004', 'utility.gas.pipeline', 'utility.gas.pipeline', '21000000-0000-0000-0000-000000000005', 'Газопровод', true),
  ('22000000-0000-0000-0000-000000000005', 'utility.power.cable', 'utility.power.cable', '21000000-0000-0000-0000-000000000006', 'Силовой кабель', true),
  ('22000000-0000-0000-0000-000000000006', 'utility.power.overhead', 'utility.power.overhead', '21000000-0000-0000-0000-000000000006', 'Воздушная линия', true),
  ('22000000-0000-0000-0000-000000000007', 'utility.sewer.pipeline', 'utility.sewer.pipeline', '21000000-0000-0000-0000-000000000007', 'Канализационный трубопровод', true),
  ('22000000-0000-0000-0000-000000000008', 'utility.telecom.cable', 'utility.telecom.cable', '21000000-0000-0000-0000-000000000008', 'Кабель связи', true),
  ('22000000-0000-0000-0000-000000000009', 'vegetation.existing.tree', 'vegetation.existing.tree', '21000000-0000-0000-0000-000000000009', 'Существующее дерево', true),
  ('22000000-0000-0000-0000-000000000010', 'vegetation.existing.shrub', 'vegetation.existing.shrub', '21000000-0000-0000-0000-000000000009', 'Существующий кустарник', true),
  ('22000000-0000-0000-0000-000000000011', 'vegetation.proposed.tree', 'vegetation.proposed.tree', '21000000-0000-0000-0000-000000000010', 'Проектируемое дерево', true),
  ('22000000-0000-0000-0000-000000000012', 'vegetation.proposed.shrub', 'vegetation.proposed.shrub', '21000000-0000-0000-0000-000000000010', 'Проектируемый кустарник', true)
ON CONFLICT (code) DO NOTHING;

INSERT INTO rules.intervention_classes(id, code, path, parent_id, title) VALUES
  ('30000000-0000-0000-0000-000000000001', 'planting', 'planting', NULL, 'Посадка'),
  ('30000000-0000-0000-0000-000000000002', 'soil', 'soil', NULL, 'Работа с грунтом')
ON CONFLICT (code) DO NOTHING;

INSERT INTO rules.intervention_classes(id, code, path, parent_id, title) VALUES
  ('31000000-0000-0000-0000-000000000001', 'planting.tree', 'planting.tree', '30000000-0000-0000-0000-000000000001', 'Посадка дерева'),
  ('31000000-0000-0000-0000-000000000002', 'planting.shrub', 'planting.shrub', '30000000-0000-0000-0000-000000000001', 'Посадка кустарника'),
  ('31000000-0000-0000-0000-000000000003', 'planting.grass', 'planting.grass', '30000000-0000-0000-0000-000000000001', 'Устройство газона'),
  ('31000000-0000-0000-0000-000000000004', 'planting.flowerbed', 'planting.flowerbed', '30000000-0000-0000-0000-000000000001', 'Устройство цветника'),
  ('31000000-0000-0000-0000-000000000005', 'soil.excavation', 'soil.excavation', '30000000-0000-0000-0000-000000000002', 'Выемка грунта'),
  ('31000000-0000-0000-0000-000000000006', 'soil.fill', 'soil.fill', '30000000-0000-0000-0000-000000000002', 'Отсыпка грунта')
ON CONFLICT (code) DO NOTHING;

INSERT INTO ops.schema_migrations(version, description)
VALUES ('0002', 'Seed object classes, intervention classes and biological definitions');

COMMIT;
