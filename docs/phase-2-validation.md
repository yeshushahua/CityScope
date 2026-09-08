# Phase 2 验证记录

验证日期：2026-09-08。

## 环境

| 组件 | 实际版本 |
| --- | --- |
| Docker Desktop | 4.90.0.238679 |
| Docker Engine / CLI | 29.7.2 |
| Docker Compose | v5.5.1 |
| PostgreSQL | 16.4 |
| PostGIS | 3.4.3 |
| Python | 3.12.14 |
| OSMnx | 2.1.1 |
| Node.js | 24.19.0 |
| npm | 11.17.0 |

Docker CLI 安装在 `C:\Program Files\Docker\Docker\resources\bin\docker.exe`；当前 Codex 进程的 PATH 未包含该目录，因此验证时使用完整路径。Docker Desktop Engine 与 WSL2 `docker-desktop` 均正常运行。

真实执行 `SELECT version()` 返回 PostgreSQL 16.4；`SELECT PostGIS_Full_Version()` 返回 PostGIS 3.4.3（含 GEOS 3.12.1）。

## 数据

- 来源：OpenStreetMap contributors
- Demo bbox：`(103.60, 35.98, 104.08, 36.16)`，兰州市连续主城区及周边建成区
- 源与存储 CRS：EPSG:4326
- 建筑面积计算 CRS：EPSG:32648
- 缓存数据最后获取时间：2026-09-08T03:48:12.739305+00:00
- 缓存：1 个道路 GraphML、6 个建筑 GeoPackage 分块、6 个 POI GeoPackage 分块

清洗与导入真实结果：

| 数据集 | 下载/缓存记录 | 有效记录 | 移除 | PostGIS 行数 |
| --- | ---: | ---: | ---: | ---: |
| road_nodes | 8,286 | 8,286 | 0 | 8,286 |
| road_edges | 18,441 | 18,441 | 0 | 18,441 |
| buildings | 30,012 | 30,011 | 1 | 30,011 |
| pois | 2,308 | 2,308 | 0 | 2,308 |

建筑下载数 30,012 与有效数 30,011 的差异来自 OSM `node 4928315421`：该记录带有 `building` 标签，但 geometry 是有效 Point，无法写入只接受建筑面的 MULTIPOLYGON 表，因此按明确的 geometry type 规则移除。

POI 分类统计：

| category | 数量 |
| --- | ---: |
| transport | 1,424 |
| education | 378 |
| commercial | 176 |
| recreation | 176 |
| healthcare | 102 |
| public_safety | 48 |
| emergency | 4 |

`data/sample/lanzhou_osm_sample.geojson` 从 PostGIS 导出 10 个 POI 与 5 个建筑，共 15 个真实要素，文件 17,204 bytes。

## 数据库

| 表 | geometry | SRID | 行数 | 空间索引 |
| --- | --- | ---: | ---: | --- |
| road_nodes | POINT | 4326 | 8,286 | `idx_road_nodes_geometry` GiST |
| road_edges | LINESTRING | 4326 | 18,441 | `idx_road_edges_geometry` GiST |
| buildings | MULTIPOLYGON | 4326 | 30,011 | `idx_buildings_geometry` GiST |
| pois | POINT | 4326 | 2,308 | `idx_pois_geometry` GiST |

`pois.category` 与 `pois.subcategory` 另有 B-tree 索引。四表 `ST_IsValid` 检查的无效几何数量均为 0；POI、建筑和道路身份字段有唯一约束。

ETL 以 `--replace` 连续执行两次，第二次全部命中缓存，四表计数与第一次完全一致，没有翻倍。JSONB 原始标签使用标准 JSON 写入。

## API

| Endpoint | 真实测试结果 |
| --- | --- |
| `GET /api/v1/health` | 200，既有响应保持不变 |
| `GET /api/v1/health/database` | 200，PostgreSQL / PostGIS 可用 |
| `GET /api/v1/layers/pois` | 200，标准 GeoJSON FeatureCollection |
| `GET /api/v1/layers/pois?category=healthcare` | 200，仅返回 healthcare |
| `GET /api/v1/layers/buildings?bbox=103.82,36.04,103.84,36.06` | 200，返回真实建筑 |
| 大范围或缺失建筑 bbox | 422，明确拒绝 |

POI bbox 点坐标、分类一致性、建筑 bbox 限制、GeoJSON 结构均由真实 PostGIS 集成测试覆盖。API 查询使用 `ST_Intersects`、`ST_MakeEnvelope` 和 `ST_AsGeoJSON`。

## 前端

- POI 默认显示，研究区实际从 API 加载 2,307 个点；分类使用不同圆点颜色。
- POI 开关在真实浏览器中成功隐藏并恢复点图层。
- 点击 POI 显示真实名称或“未命名兴趣点”、category、subcategory、OSM 类型与 ID。
- 建筑默认关闭；开启后低于 zoom 14 不请求数据，高缩放按 viewport bbox 加载。
- 浏览器验收中建筑首次加载 141 个；拖动地图触发 `moveend` 后更新为 146 个。
- 连续视窗请求使用 AbortController 取消旧请求，避免过期响应覆盖新数据。
- API 与 PostGIS 状态均来自真实健康接口；Attribution 保留。

## 测试

- `pytest -q`：11 passed；包含真实 PostGIS 集成测试。
- `npm run build`：TypeScript 和 Vite 构建通过，97 modules transformed。
- `npm run dev`：开发版实际启动并完成图层、Popup、缩放、移动测试。
- `npm run preview -- --host 127.0.0.1 --port 4173 --strictPort`：生产预览 200，加载 2,307 个 POI。
- 生产预览浏览器 Console：关键 Error 0。
- 数据库验证：四表计数、geometry_columns、SRID、`ST_IsValid`、GiST 和 POI 分类统计均实际查询通过。

## 已知问题

- OSM 覆盖由社区维护，分类数量代表本次获取结果，不代表权威或完整设施名录。
- 前端展示研究区 bbox 内 2,307 个 POI，数据库共 2,308 个。例外是 OSM relation `19103914`：其 MultiPolygon 由相距很远的离散成员组成，bounds 为 `(102.6991471, 25.0697086, 113.6939346, 36.034902)`，与下载范围相交，但转换后的代表点为 `(113.5671427, 34.8166042)`，位于研究区外，因此被 PostGIS bbox 查询正确排除；没有人为移动坐标。
- OpenFreeMap Liberty 偶尔记录缺少个别底图 sprite 图标的 warning，不影响 CityScope POI/建筑图层；生产预览无关键 Error。
- Vite 提示主 JavaScript chunk 超过 500 kB。Phase 2 交互正常，后续模块增多时再按功能拆包。
- pytest 有 Starlette/AnyIO 第三方弃用提示，不影响 11 项测试通过。
- Codex 沙箱内运行 pytest 时另有两条 `.pytest_cache` 写入权限 warning；不影响测试与应用文件，普通本地终端不受该沙箱限制。

## 结论

Phase 2 - Completed / PASS。
