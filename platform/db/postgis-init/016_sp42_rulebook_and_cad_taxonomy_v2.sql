\set ON_ERROR_STOP on
BEGIN;

-- Stable physical classes: lifecycle and CAD representation belong to separate axes.
INSERT INTO geo.object_classes(code,path,parent_id,title,is_constraint_source)
SELECT v.code, v.code::ltree, p.id, v.title, v.constraint_source
FROM (VALUES
 ('vegetation.tree','vegetation','Дерево',true),
 ('vegetation.shrub','vegetation','Кустарник',true),
 ('vegetation.grass','vegetation','Травянистая растительность и газон',false),
 ('vegetation.mixed','vegetation','Смешанные зелёные насаждения',true),
 ('structure.wall','structure','Стена',true),
 ('structure.support','structure','Опора или мачта',true),
 ('structure.retaining_wall','structure','Подпорная стенка',true),
 ('transport.pedestrian','transport','Пешеходная инфраструктура',true),
 ('transport.tram','transport','Трамвайная инфраструктура',true),
 ('transport.cycleway','transport','Велосипедная инфраструктура',true),
 ('transport.ditch','transport','Канава',true),
 ('utility.heat','utility','Тепловая сеть',true),
 ('utility.drainage','utility','Дренаж и водосток',true),
 ('terrain.slope_toe','terrain','Подошва откоса или бровка террасы',true),
 ('terrain.groundwater_level','terrain','Уровень грунтовых вод',true),
 ('territory.visibility_zone','territory','Зона видимости',true),
 ('territory.metro_technical_zone','territory','Техническая зона метрополитена',true),
 ('territory.sanitary_protection_zone','territory','Санитарно-защитная зона',true),
 ('territory.utility_protection_zone','territory','Охранная зона инженерной сети',true)
) v(code,parent_code,title,constraint_source)
JOIN geo.object_classes p ON p.code=v.parent_code
ON CONFLICT (code) DO UPDATE SET title=EXCLUDED.title, is_constraint_source=EXCLUDED.is_constraint_source;

INSERT INTO geo.object_classes(code,path,parent_id,title,is_constraint_source)
SELECT v.code, v.code::ltree, p.id, v.title, true
FROM (VALUES
 ('structure.wall.external','structure.wall','Наружная стена здания'),
 ('transport.road.edge','transport.road','Край проезжей части или укреплённой полосы обочины'),
 ('transport.pedestrian.path_edge','transport.pedestrian','Край тротуара или садовой дорожки'),
 ('transport.tram.track_edge','transport.tram','Край трамвайного полотна'),
 ('transport.cycleway.edge','transport.cycleway','Край велосипедной дорожки'),
 ('transport.ditch.edge','transport.ditch','Бровка канавы'),
 ('utility.heat.pipeline','utility.heat','Теплопровод'),
 ('utility.drainage.pipeline','utility.drainage','Дренажный или водосточный трубопровод')
) v(code,parent_code,title)
JOIN geo.object_classes p ON p.code=v.parent_code
ON CONFLICT (code) DO UPDATE SET title=EXCLUDED.title, is_constraint_source=true;

-- Old codes remain resolvable for history but are not valid new review choices.
UPDATE geo.object_classes SET is_constraint_source=false
WHERE code IN ('vegetation.existing','vegetation.proposed','surface.lawn');

UPDATE intake.classification_taxonomies SET status='retired' WHERE version='cad-v1';
INSERT INTO intake.classification_taxonomies(version,title,schema,status)
VALUES ('cad-v2-sp42','GreenPlan CAD taxonomy aligned with SP 42.13330.2016',
 '{"axes":["domain","lifecycle","representation","object_class","document_role"],"object_class_is_lifecycle_independent":true,"closed_object_class_vocabulary":true,"allow_unknown":true,"allow_not_applicable":true}'::jsonb,'active')
ON CONFLICT (version) DO UPDATE SET title=EXCLUDED.title,schema=EXCLUDED.schema,status='active';

INSERT INTO intake.classification_labels(taxonomy_version,axis,code,title,definition)
SELECT 'cad-v2-sp42',v.axis,v.code,v.title,v.definition FROM (VALUES
 ('domain','vegetation','Растительность','Живые растения и насаждения'),
 ('domain','transport','Транспорт','Улицы, пути и дорожки'),
 ('domain','utility','Инженерные сети','Подземные и надземные коммуникации'),
 ('domain','building','Здания','Здания и инженерные сооружения'),
 ('domain','terrain','Рельеф','Рельеф и грунтовые воды'),
 ('domain','boundary','Границы','Границы работ'),
 ('domain','protection_zone','Регламентные зоны','Охранные, санитарные и технические зоны'),
 ('domain','annotation','Аннотации','Текст и оформление'),
 ('domain','mixed','Смешанный слой','Несколько предметных областей'),
 ('domain','unknown','Не определено','Недостаточно данных'),
 ('lifecycle','existing','Существующее','Существующее состояние'),
 ('lifecycle','proposed','Проектируемое','Проектное решение'),
 ('lifecycle','demolition','Удаляемое','Снос или вырубка'),
 ('lifecycle','replacement','Заменяемое','Замена или пересадка'),
 ('lifecycle','reference','Справочное','Подоснова или XREF'),
 ('lifecycle','mixed','Смешанный','Несколько состояний'),
 ('lifecycle','unknown','Не определено','Состояние не установлено'),
 ('representation','point','Точка','Позиция объекта'),
 ('representation','centerline','Осевая линия','Ось линейного объекта'),
 ('representation','edge','Край','Нормативно значимая кромка'),
 ('representation','footprint','Контур','Пятно объекта'),
 ('representation','crown','Крона','Проекция кроны'),
 ('representation','hatch','Заливка','Штриховка или заливка'),
 ('representation','symbol','Условный знак','Условное обозначение'),
 ('representation','text','Текст','Текстовая аннотация'),
 ('representation','dimension','Размер','Размерная линия'),
 ('representation','legend','Легенда','Условные обозначения'),
 ('representation','sheet_frame','Штамп или рамка','Оформление листа'),
 ('representation','construction','Вспомогательная графика','Непредметная геометрия'),
 ('representation','mixed','Смешанное представление','Несколько представлений'),
 ('representation','unknown','Не определено','Представление не установлено'),
 ('object_class','unknown','Не определено','Требует инженерной классификации'),
 ('object_class','not_applicable','Неприменимо','Не является физическим объектом'),
 ('document_role','survey','Обследование','Существующее состояние'),
 ('document_role','general_plan','Генеральный план','Проектный генеральный план'),
 ('document_role','dendroplan','Дендроплан','Проект озеленения'),
 ('document_role','source_base','Исходная подоснова','Исходные данные'),
 ('document_role','xref','Внешняя ссылка','Зависимость CAD'),
 ('document_role','printable_sheet','Печатный лист','Лист для выпуска'),
 ('document_role','unknown','Не определено','Роль не установлена'),
 ('document_role','not_applicable','Неприменимо','Роль отсутствует')
) v(axis,code,title,definition)
ON CONFLICT (taxonomy_version,axis,code) DO UPDATE SET title=EXCLUDED.title,definition=EXCLUDED.definition;

INSERT INTO intake.classification_labels(taxonomy_version,axis,code,title,definition)
SELECT 'cad-v2-sp42','object_class',o.code,o.title,'Канонический класс пространственного объекта'
FROM geo.object_classes o WHERE o.code IN (
 'vegetation.tree','vegetation.shrub','vegetation.grass','vegetation.mixed',
 'structure.building','structure.wall.external','structure.support','structure.retaining_wall',
 'transport.road.carriageway','transport.road.edge','transport.road.curb','transport.pedestrian.path_edge',
 'transport.tram.track_edge','transport.cycleway.edge','transport.ditch.edge',
 'utility.water.pipeline','utility.drainage.pipeline','utility.sewer.pipeline','utility.heat.pipeline',
 'utility.gas.pipeline','utility.power.cable','utility.power.overhead','utility.telecom.cable',
 'territory.work_boundary','territory.visibility_zone','territory.metro_technical_zone',
 'territory.sanitary_protection_zone','territory.utility_protection_zone',
 'terrain.slope_toe','terrain.groundwater_level','terrain')
ON CONFLICT (taxonomy_version,axis,code) DO UPDATE SET title=EXCLUDED.title;

INSERT INTO rules.jurisdictions(code,title,properties) VALUES ('RU','Российская Федерация','{}')
ON CONFLICT (code) DO NOTHING;
INSERT INTO rules.regulatory_documents(code,title,document_kind,jurisdiction_id,status,properties)
SELECT 'SP-42.13330.2016','СП 42.13330.2016. Градостроительство. Планировка и застройка городских и сельских поселений','code_of_practice',id,'unknown',
 '{"local_path":"docs/sp42-13330-2016.pdf","verification_note":"Local copy; legal currency and official provenance require human verification"}'::jsonb
FROM rules.jurisdictions WHERE code='RU'
ON CONFLICT (code) DO UPDATE SET title=EXCLUDED.title,properties=EXCLUDED.properties;
INSERT INTO rules.document_editions(document_id,edition_label,sha256,status,retrieved_at,media_type,access_policy,acquisition_note)
SELECT id,'local-copy-f059645c-2026-09-29','f059645cab53219a5825d1fe5a15780926628c1a1e62937e0895b572b302d106','unverified',now(),'application/pdf','internal_copy',
 'Provided by project team. Printed copy mentions changes N1/N2; compare with an official current edition before approval.'
FROM rules.regulatory_documents WHERE code='SP-42.13330.2016'
ON CONFLICT (document_id,edition_label) DO UPDATE SET sha256=EXCLUDED.sha256,status='unverified',acquisition_note=EXCLUDED.acquisition_note;

INSERT INTO rules.provisions(edition_id,locator,heading,verified_excerpt,status)
SELECT e.id,v.locator,v.heading,v.excerpt,'draft'
FROM rules.document_editions e JOIN rules.regulatory_documents d ON d.id=e.document_id
CROSS JOIN (VALUES
 ('9.6 table 9.1','Distances from buildings, structures and utilities to trees and shrubs','Values transcribed from table 9.1; source wording must be verified.'),
 ('9.6 table 9.1 note 1','Tree crown over 5 m','Distances are for trees with crown diameter up to 5 m; larger crowns require an increase.'),
 ('9.6 table 9.1 note 2','Overhead lines','Distances to overhead lines are governed by referenced external rules.'),
 ('9.6 table 9.1 note 3','Insolation and daylight','Trees near buildings must not impede insolation and daylight requirements.'),
 ('9.6 table 9.1 notes 4-7','Root barriers and designed protection','Special reductions and root barriers require explicit project conditions.'),
 ('8.6','Landscaping of sanitary protection zones','Minimum landscaped shares depend on sanitary-zone width; protective strip is required.'),
 ('11.14','Cycleway clearance','Minimum distance from cycleway edge to tree is 0.75 m.'),
 ('11.16','Visibility triangles','Objects and vegetation higher than 0.5 m are not allowed in sight triangles.'),
 ('11.27','Shallow metro technical zone','Tree planting is prohibited until construction completion.'),
 ('13.2','Preservation in vertical planning','Vertical planning should maximize preservation of existing trees.'),
 ('13.4','Groundwater lowering','For parks, squares and greenery, groundwater must be at least 1 m below design surface.'),
 ('13.7, 13.9','Protective vegetation','Vegetation may be required for mudflow and landslide protection.'),
 ('14.20, 14.21','Microclimate and insolation','Landscaping must consider microclimate and insolation.')
) v(locator,heading,excerpt)
WHERE d.code='SP-42.13330.2016' AND e.edition_label='local-copy-f059645c-2026-09-29'
ON CONFLICT (edition_id,locator) DO UPDATE SET heading=EXCLUDED.heading,verified_excerpt=EXCLUDED.verified_excerpt,status='draft';

-- Exactly 19 non-empty cells of table 9.1. Dashes are intentionally not encoded as zero.
WITH source(code,subject_code,object_codes,distance_m,geometry_operator,measure_to) AS (VALUES
 ('sp42.9_1.base.external_wall.tree','planting.tree',ARRAY['structure.wall.external'],5.0,'buffer_footprint','axis'),
 ('sp42.9_1.base.external_wall.shrub','planting.shrub',ARRAY['structure.wall.external'],1.5,'buffer_footprint','axis'),
 ('sp42.9_1.base.tram_edge.tree','planting.tree',ARRAY['transport.tram.track_edge'],5.0,'buffer_centerline','axis'),
 ('sp42.9_1.base.tram_edge.shrub','planting.shrub',ARRAY['transport.tram.track_edge'],3.0,'buffer_centerline','axis'),
 ('sp42.9_1.base.path_edge.tree','planting.tree',ARRAY['transport.pedestrian.path_edge'],0.7,'buffer_centerline','axis'),
 ('sp42.9_1.base.path_edge.shrub','planting.shrub',ARRAY['transport.pedestrian.path_edge'],0.5,'buffer_centerline','axis'),
 ('sp42.9_1.base.road_edge.tree','planting.tree',ARRAY['transport.road.edge'],2.0,'buffer_centerline','axis'),
 ('sp42.9_1.base.road_edge.shrub','planting.shrub',ARRAY['transport.road.edge'],1.0,'buffer_centerline','axis'),
 ('sp42.9_1.base.support.tree','planting.tree',ARRAY['structure.support'],4.0,'buffer_footprint','axis'),
 ('sp42.9_1.base.slope_toe.tree','planting.tree',ARRAY['terrain.slope_toe'],1.0,'buffer_centerline','axis'),
 ('sp42.9_1.base.slope_toe.shrub','planting.shrub',ARRAY['terrain.slope_toe'],0.5,'buffer_centerline','axis'),
 ('sp42.9_1.base.retaining_wall.tree','planting.tree',ARRAY['structure.retaining_wall'],3.0,'buffer_footprint','axis'),
 ('sp42.9_1.base.retaining_wall.shrub','planting.shrub',ARRAY['structure.retaining_wall'],1.0,'buffer_footprint','axis'),
 ('sp42.9_1.base.gas_sewer.tree','planting.tree',ARRAY['utility.gas.pipeline','utility.sewer.pipeline'],1.5,'buffer_centerline','external_surfaces'),
 ('sp42.9_1.base.heat.tree','planting.tree',ARRAY['utility.heat.pipeline'],2.0,'buffer_centerline','external_surfaces'),
 ('sp42.9_1.base.heat.shrub','planting.shrub',ARRAY['utility.heat.pipeline'],1.0,'buffer_centerline','external_surfaces'),
 ('sp42.9_1.base.water_drainage.tree','planting.tree',ARRAY['utility.water.pipeline','utility.drainage.pipeline'],2.0,'buffer_centerline','external_surfaces'),
 ('sp42.9_1.base.power_telecom.tree','planting.tree',ARRAY['utility.power.cable','utility.telecom.cable'],2.0,'buffer_centerline','external_surfaces'),
 ('sp42.9_1.base.power_telecom.shrub','planting.shrub',ARRAY['utility.power.cable','utility.telecom.cable'],0.7,'buffer_centerline','external_surfaces')
), context AS (
 SELECT p.id provision_id,j.id jurisdiction_id FROM rules.provisions p
 JOIN rules.document_editions e ON e.id=p.edition_id JOIN rules.regulatory_documents d ON d.id=e.document_id
 JOIN rules.jurisdictions j ON j.code='RU'
 WHERE d.code='SP-42.13330.2016' AND p.locator='9.6 table 9.1'
)
INSERT INTO rules.rules(code,status,provision_id,jurisdiction_id,effect_type,geometry_operator,distance_m,comparison_operator,priority,conditions,safety_critical)
SELECT s.code,'review',c.provision_id,c.jurisdiction_id,'minimum_clearance',s.geometry_operator,s.distance_m,'>=',10,
 jsonb_build_object('source_table','9.1','measure_to',s.measure_to,'crown_diameter_m_max',5,'requires_verified_source',true),true
FROM source s CROSS JOIN context c ON CONFLICT (code) DO UPDATE SET distance_m=EXCLUDED.distance_m,conditions=EXCLUDED.conditions,status='review';

WITH source(code,subject_code) AS (VALUES
 ('sp42.9_1.base.external_wall.tree','planting.tree'),('sp42.9_1.base.external_wall.shrub','planting.shrub'),
 ('sp42.9_1.base.tram_edge.tree','planting.tree'),('sp42.9_1.base.tram_edge.shrub','planting.shrub'),
 ('sp42.9_1.base.path_edge.tree','planting.tree'),('sp42.9_1.base.path_edge.shrub','planting.shrub'),
 ('sp42.9_1.base.road_edge.tree','planting.tree'),('sp42.9_1.base.road_edge.shrub','planting.shrub'),
 ('sp42.9_1.base.support.tree','planting.tree'),('sp42.9_1.base.slope_toe.tree','planting.tree'),
 ('sp42.9_1.base.slope_toe.shrub','planting.shrub'),('sp42.9_1.base.retaining_wall.tree','planting.tree'),
 ('sp42.9_1.base.retaining_wall.shrub','planting.shrub'),('sp42.9_1.base.gas_sewer.tree','planting.tree'),
 ('sp42.9_1.base.heat.tree','planting.tree'),('sp42.9_1.base.heat.shrub','planting.shrub'),
 ('sp42.9_1.base.water_drainage.tree','planting.tree'),('sp42.9_1.base.power_telecom.tree','planting.tree'),
 ('sp42.9_1.base.power_telecom.shrub','planting.shrub'))
INSERT INTO rules.rule_subject_classes(rule_id,intervention_class_id)
SELECT r.id,i.id FROM source s JOIN rules.rules r ON r.code=s.code JOIN rules.intervention_classes i ON i.code=s.subject_code
ON CONFLICT DO NOTHING;

WITH source(code,object_codes) AS (VALUES
 ('sp42.9_1.base.external_wall.tree',ARRAY['structure.wall.external']),('sp42.9_1.base.external_wall.shrub',ARRAY['structure.wall.external']),
 ('sp42.9_1.base.tram_edge.tree',ARRAY['transport.tram.track_edge']),('sp42.9_1.base.tram_edge.shrub',ARRAY['transport.tram.track_edge']),
 ('sp42.9_1.base.path_edge.tree',ARRAY['transport.pedestrian.path_edge']),('sp42.9_1.base.path_edge.shrub',ARRAY['transport.pedestrian.path_edge']),
 ('sp42.9_1.base.road_edge.tree',ARRAY['transport.road.edge']),('sp42.9_1.base.road_edge.shrub',ARRAY['transport.road.edge']),
 ('sp42.9_1.base.support.tree',ARRAY['structure.support']),('sp42.9_1.base.slope_toe.tree',ARRAY['terrain.slope_toe']),
 ('sp42.9_1.base.slope_toe.shrub',ARRAY['terrain.slope_toe']),('sp42.9_1.base.retaining_wall.tree',ARRAY['structure.retaining_wall']),
 ('sp42.9_1.base.retaining_wall.shrub',ARRAY['structure.retaining_wall']),('sp42.9_1.base.gas_sewer.tree',ARRAY['utility.gas.pipeline','utility.sewer.pipeline']),
 ('sp42.9_1.base.heat.tree',ARRAY['utility.heat.pipeline']),('sp42.9_1.base.heat.shrub',ARRAY['utility.heat.pipeline']),
 ('sp42.9_1.base.water_drainage.tree',ARRAY['utility.water.pipeline','utility.drainage.pipeline']),
 ('sp42.9_1.base.power_telecom.tree',ARRAY['utility.power.cable','utility.telecom.cable']),
 ('sp42.9_1.base.power_telecom.shrub',ARRAY['utility.power.cable','utility.telecom.cable']))
INSERT INTO rules.rule_object_classes(rule_id,object_class_id,include_descendants)
SELECT r.id,o.id,false FROM source s CROSS JOIN LATERAL unnest(s.object_codes) AS object_code(value)
JOIN rules.rules r ON r.code=s.code JOIN geo.object_classes o ON o.code=object_code.value
ON CONFLICT DO NOTHING;

-- Clauses whose geometry or conditions cannot be safely reduced to one number.
WITH source(code,locator,effect,operator,distance,conditions) AS (VALUES
 ('sp42.9_1.review.large_crown','9.6 table 9.1 note 1','require_review','custom_review',NULL::numeric,'{"when":{"crown_diameter_m_gt":5},"reason":"increase is required but amount is not specified"}'::jsonb),
 ('sp42.9_1.review.overhead','9.6 table 9.1 note 2','require_review','custom_review',NULL,'{"external_reference":"[10]","reason":"source must be ingested separately"}'),
 ('sp42.9_1.review.insolation','9.6 table 9.1 note 3','require_review','custom_review',NULL,'{"checks":["insolation","daylight"]}'),
 ('sp42.9_1.review.root_barrier','9.6 table 9.1 notes 4-7','allow_with_conditions','custom_review',NULL,'{"root_barrier_clearance_m":0.5,"tree_height_bands_m":[5,20],"engineered_measure_required":true}'),
 ('sp42.8_6.review.sanitary_zone','8.6','require_review','inside',NULL,'{"landscaped_share_by_zone_width":[{"width_m_lte":300,"min_percent":60},{"width_m_lte":1000,"min_percent":50},{"width_m_lte":3000,"min_percent":40},{"width_m_gt":3000,"min_percent":20}],"protective_strip_m":{"default":50,"zone_width_m_lte_100":20}}'),
 ('sp42.11_14.cycleway.tree','11.14','minimum_clearance','buffer_centerline',0.75,'{"measure_from":"cycleway_edge"}'),
 ('sp42.11_16.visibility','11.16','prohibit','inside',NULL,'{"height_m_gt":0.5,"applies_to":["tree","shrub"]}'),
 ('sp42.11_27.metro.tree','11.27','prohibit','inside',NULL,'{"until":"metro_construction_completed"}'),
 ('sp42.13_2.preserve_existing','13.2','require_review','custom_review',NULL,'{"goal":"maximize_preservation_of_existing_trees"}'),
 ('sp42.13_4.groundwater','13.4','minimum_clearance','vertical_clearance',1.0,'{"measure_from":"design_surface","direction":"down"}'),
 ('sp42.13_7_13_9.protective_vegetation','13.7, 13.9','require_review','custom_review',NULL,'{"hazards":["mudflow","landslide"]}'),
 ('sp42.14_20_14_21.microclimate','14.20, 14.21','require_review','custom_review',NULL,'{"checks":["microclimate","insolation"]}')
), context AS (
 SELECT p.id provision_id,p.locator,j.id jurisdiction_id FROM rules.provisions p
 JOIN rules.document_editions e ON e.id=p.edition_id JOIN rules.regulatory_documents d ON d.id=e.document_id
 JOIN rules.jurisdictions j ON j.code='RU' WHERE d.code='SP-42.13330.2016'
)
INSERT INTO rules.rules(code,status,provision_id,jurisdiction_id,effect_type,geometry_operator,distance_m,comparison_operator,priority,conditions,safety_critical)
SELECT s.code,'review',c.provision_id,c.jurisdiction_id,s.effect,s.operator,s.distance,
 CASE WHEN s.distance IS NULL THEN NULL ELSE '>=' END,20,s.conditions || '{"requires_verified_source":true}',true
FROM source s JOIN context c ON c.locator=s.locator
ON CONFLICT (code) DO UPDATE SET conditions=EXCLUDED.conditions,status='review',distance_m=EXCLUDED.distance_m;

-- Broad mappings for non-tabular checks; a reviewer may refine them before approval.
INSERT INTO rules.rule_subject_classes(rule_id,intervention_class_id)
SELECT r.id,i.id FROM rules.rules r CROSS JOIN rules.intervention_classes i
WHERE r.code LIKE 'sp42.%' AND r.code NOT LIKE 'sp42.9_1.base.%'
  AND i.code IN ('planting.tree','planting.shrub')
ON CONFLICT DO NOTHING;

INSERT INTO rules.rule_object_classes(rule_id,object_class_id,include_descendants)
SELECT r.id,o.id,false FROM rules.rules r JOIN geo.object_classes o ON
 (r.code='sp42.11_14.cycleway.tree' AND o.code='transport.cycleway.edge') OR
 (r.code='sp42.11_16.visibility' AND o.code='territory.visibility_zone') OR
 (r.code='sp42.11_27.metro.tree' AND o.code='territory.metro_technical_zone') OR
 (r.code='sp42.13_4.groundwater' AND o.code='terrain.groundwater_level') OR
 (r.code='sp42.8_6.review.sanitary_zone' AND o.code='territory.sanitary_protection_zone') OR
 (r.code='sp42.9_1.review.overhead' AND o.code='utility.power.overhead') OR
 (r.code IN ('sp42.9_1.review.large_crown','sp42.9_1.review.insolation','sp42.9_1.review.root_barrier') AND o.code='structure.building')
ON CONFLICT DO NOTHING;

INSERT INTO rules.rule_sets(code,version_no,title,status,content_fingerprint)
VALUES ('sp42-landscaping-local-review',1,'SP 42 landscaping rules from unverified local copy','draft',
 'f059645cab53219a5825d1fe5a15780926628c1a1e62937e0895b572b302d106:landscaping:v1')
ON CONFLICT (code,version_no) DO UPDATE SET title=EXCLUDED.title,status='draft';
INSERT INTO rules.rule_set_members(rule_set_id,rule_id)
SELECT rs.id,r.id FROM rules.rule_sets rs CROSS JOIN rules.rules r
WHERE rs.code='sp42-landscaping-local-review' AND rs.version_no=1 AND r.code LIKE 'sp42.%'
ON CONFLICT DO NOTHING;

DO $$
BEGIN
 IF (SELECT count(*) FROM rules.rules WHERE code LIKE 'sp42.9_1.base.%') <> 19 THEN
   RAISE EXCEPTION 'SP42 table 9.1 must contain exactly 19 non-null rules';
 END IF;
 IF EXISTS (SELECT 1 FROM rules.rules WHERE code LIKE 'sp42.%' AND status <> 'review') THEN
   RAISE EXCEPTION 'Unverified SP42 rules must remain in review';
 END IF;
 IF EXISTS (SELECT 1 FROM rules.rules WHERE code LIKE 'sp42.9_1.base.%' AND (distance_m IS NULL OR distance_m=0)) THEN
   RAISE EXCEPTION 'A table dash must never become zero or a numeric rule';
 END IF;
END $$;

INSERT INTO ops.schema_migrations(version,description)
VALUES ('016','SP42 landscaping review rules and lifecycle-independent CAD taxonomy v2')
ON CONFLICT (version) DO NOTHING;
COMMIT;
