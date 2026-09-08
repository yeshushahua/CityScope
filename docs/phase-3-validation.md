# Phase 3 验证记录

验证日期：2026-09-08。

## Phase 3 目标

Phase 3 在 Phase 2 的真实兰州 OSM/PostGIS 数据上增加基础空间查询：用户点击地图选择 WGS84 中心点，以米为单位设置半径，由 PostGIS 返回附近 POI、分类汇总、相交建筑数量和范围内实际建筑占地面积。没有实现路网、路径、出行时间或应急调度。

## API 与参数

### `GET /api/v1/spatial/nearby-pois`

| 参数 | 规则 |
| --- | --- |
| `lon` | 必填，103–105 |
| `lat` | 必填，35–37 |
| `radius_m` | 默认 1000，100–10000 |
| `category` | 可选，7 个规范类别之一 |
| `subcategory` | 可选，18 个当前 ETL 子类别之一 |
| `limit` | 默认 100，1–200 |

返回标准 GeoJSON FeatureCollection，properties 包括真实 OSM 身份、category、subcategory 和一位小数的 `distance_m`，并附带 center、radius 和返回数量 meta。结果按 `distance_m, id` 升序。

### `GET /api/v1/spatial/summary`

参数为 `lon`、`lat`、`radius_m`，规则相同。返回 POI 总数与 `GROUP BY category` 统计，以及相交建筑数量和查询圆范围内实际建筑占地面积。

非法坐标、半径、limit、category、subcategory 或不匹配的 category/subcategory 返回 422；空结果返回 200 和空 FeatureCollection/零统计。数据库查询异常返回 503，不生成替代数据。

## PostGIS 查询方法

查询点使用：

```sql
ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
```

附近 POI 使用 `ST_DWithin(geometry::geography, point::geography, radius_m)` 过滤，使用 `ST_Distance` geography 计算米制距离。这是 WGS84 椭球上的测地直线距离，不是道路距离、出行距离或响应时间。

查询范围由 `ST_Buffer(point::geography, radius_m)::geometry` 在数据库中构造。前端生成的圆只负责显示，不参与正式统计。

POI 汇总在 PostgreSQL 中使用 `GROUP BY GROUPING SETS` 同时获得总数和 category 计数，没有把全表读入 Python。

## CRS 与建筑面积统计口径

- 存储和 API geometry：EPSG:4326。
- POI 距离与半径：PostGIS geography，单位米。
- 建筑数量：与数据库构造的查询圆相交的建筑数量。
- 建筑面积：先执行 `ST_Intersection(building, query_area)`，再 `ST_Transform(..., 32648)`，最后 `ST_Area` 并求和。

因此 `footprint_area_m2` 只计入查询圈内的实际相交部分，没有将圆边缘外的整栋建筑面积全部计入。Phase 2 已有 `area_m2` 仍保留，用于建筑自身总面积信息。

## Phase 2 补充核查

- `GET /api/v1/layers/pois` 的 bbox、category、subcategory 和 limit 均有自动测试。
- `buildings.area_m2` 已在 ETL 中使用 EPSG:32648 计算，无需新增字段。
- 被移除的 1 条建筑是带 `building` 标签的 OSM `node 4928315421`；geometry 是 Point，不能进入 MULTIPOLYGON 建筑表。
- bbox 外 POI 是 relation `19103914`。其离散 MultiPolygon bounds 横跨 `(102.6991471, 25.0697086, 113.6939346, 36.034902)`，代表点落在 `(113.5671427, 34.8166042)`，因此 PostGIS 研究区查询正确排除。

## 索引设计与 EXPLAIN

创建索引前，1 km POI geography 查询对 2,308 行执行 Seq Scan：

- Rows Removed by Filter：2,234
- Execution Time：18.897 ms

现有 geometry GiST 不能直接服务 `geometry::geography` 表达式，因此新增：

```sql
CREATE INDEX idx_pois_geography
ON pois USING GIST ((geometry::geography));
```

创建后相同查询计划为 `Bitmap Index Scan on idx_pois_geography` → `Bitmap Heap Scan`：

- 索引候选：140
- 实际返回：74
- Execution Time：5.454 ms

1 km 建筑相交面积计划使用 `Bitmap Index Scan on idx_buildings_geometry`：

- bbox 索引候选：996
- `ST_Intersects` 后：784
- Execution Time：15.878 ms

PostgreSQL 结合表规模选择 Bitmap Scan；没有强制关闭 Seq Scan 或修改 planner 参数。geography 索引已加入 ETL，`--replace` 重建表后实际确认仍存在。

## 三个真实查询实例

| 位置 | 中心 | 半径 | POI | 建筑 | 相交占地面积 |
| --- | --- | ---: | ---: | ---: | ---: |
| 兰州市中心 | 103.8343, 36.0611 | 500 m | 19 | 230 | 163,747.8 m² |
| 研究区稀疏区域 | 103.6500, 36.1200 | 1,000 m | 3 | 55 | 111,247.6 m² |
| 研究区东北边缘 | 104.0600, 36.1500 | 3,000 m | 0 | 0 | 0.0 m² |

中心点 500 m 返回距离范围为 175.3–449.6 m，全部不超过 radius 且按升序排列。稳态真实 HTTP 样本：中心 nearby 6.216 ms、中心 summary 21.462 ms、稀疏区 nearby 5.989 ms、边缘 summary 8.633 ms。首次测量包含刚启动 Uvicorn 和连接池建立时间，未作为稳态查询时间。

## 前端与浏览器验收

- “空间查询”是独立模块，没有占用应急响应或可达性分析。
- 点击地图显示深色查询中心、绿色半透明查询圆和范围内 POI；空间查询模式隐藏全量 POI，减少视觉干扰。
- 点击位置 `(103.834648, 36.061235)` 的 1 km 查询返回 73 个 POI、770 栋建筑、682,662 m² 范围内占地。
- 切换 500 m 后更新为 19 个 POI、223 栋建筑、158,365 m²；查询圆同步缩小。
- 医疗筛选在 500 m 返回空结果并正常显示零结果状态；切换至 1 km 返回 2 个真实医院。
- 点击“兰州市第一人民医院城关医院”列表项后地图 flyTo；点击结果点 Popup 显示 healthcare/hospital、680 m 测地直线距离和 OSM way ID。
- 快速连续点击地图后，旧的两组请求被 AbortController 取消，最终中心与统计对应最后一次点击。
- 生产预览实际查询 `(103.779712, 36.059435)`，返回 64 个 POI、805 栋建筑、616,639 m²。
- 开发版和生产预览 Console 关键 Error 均为 0。

## Phase 1/2 回归

- 兰州基础地图、NavigationControl、比例尺、Attribution、坐标显示与“返回兰州”正常。
- API Online 与 PostGIS Connected 正常。
- 城市总览恢复 2,307 个研究区 POI；POI 开关可隐藏和恢复。
- 普通地图坐标 Popup 正常。
- 建筑开关正常；高缩放加载 438 个建筑，移动视窗后更新为 136 个，说明 viewport 刷新仍正常。

## 测试结果

- `pytest -q`：28 passed，包含真实 PostGIS 查询、过滤、排序、范围、空结果、异常参数、建筑统计和索引检查。
- `npm run build`：通过，100 modules transformed。
- `npm run dev`：完整交互和回归测试通过。
- `npm run preview -- --host 127.0.0.1 --port 4173 --strictPort`：生产空间查询通过。
- 可重复 ETL：缓存命中，8,286 / 18,441 / 30,011 / 2,308 计数保持不变，表达式索引重建成功。

## 数据库变化

- 新增字段：无。
- 新增表：无。
- 新增索引：`idx_pois_geography`，GiST geography 表达式索引。

## 已知问题

- 附近 POI API 最多返回前 200 个要素；summary 仍返回范围内完整总数和分类统计。
- 数据完整性和设施名称取决于 OpenStreetMap 社区覆盖。
- 前端圆是 64 段测地近似，仅用于显示；正式查询圆由 PostGIS geography 构造。
- Vite 仍提示 MapLibre 主 JavaScript chunk 超过 500 kB；当前交互和查询没有明显卡顿。
- pytest 显示一条 Starlette/AnyIO 第三方弃用提示，以及 Codex 沙箱内两条 `.pytest_cache` 写权限 warning；28 项测试均通过。

## 结论

Phase 3 - Completed / PASS。
