# Phase 8 验证记录

验证日期：2026-09-09。

## 1. 业务定义与网络选择

Phase 8 实现步行 15 分钟生活圈：用户从居住位置出发，系统用真实步行道路网络计算 5/10/15 分钟可达范围和 15 分钟内可达的基本生活服务设施。

机动车网络 `road_nodes` / `routing_edges` 来自 OSMnx `network_type="drive"`，不能表达步行道、小路、台阶等步行连接。本阶段因此从 OpenStreetMap 独立下载 OSMnx `network_type="walk"` 图，写入 `pedestrian_nodes` / `pedestrian_edges`，没有用机动车路网冒充步行网络，也没有人工生成路网或 POI。

研究范围保持 `(103.60, 35.98, 104.08, 36.16)`，数据来源为 © OpenStreetMap contributors。

## 2. 步行网络 ETL 与规模

`scripts/osm/build_pedestrian_network.py --replace` 下载或复用真实 GraphML 缓存、规范节点与显式方向边、应用 migration、事务性替换数据库内容，并重建 POI 步行接入映射。相同缓存连续执行两次，结果均为：

- 23,195 个节点；
- 59,542 条显式有向边；
- 有向边总长度 8,505,806.745 m；
- 2,303 条 POI 步行接入映射；
- 稳定 SHA-256：`dfeb23ef51723e99cd8c4d3fbece1b29729d547ae5bf3db4b16305c574d9f2bf`。

网络包含 `footway` 4,374 条、`path` 2,660 条、`pedestrian` 1,278 条、`steps` 814 条和 `track` 490 条，也保留 OSMnx walk 网络实际允许步行的其他道路类型。每条 A→B 与 B→A 边按 OSMnx 图中的实际方向分别存储，`cost=travel_time_s`、`reverse_cost=-1`，正式查询使用 `directed=true`。

## 3. 数据质量与拓扑

数据库检查结果：NULL source/target 0，非法或空 geometry 0，错误 SRID 0，非正 length/speed/travel time/cost 0，source/target 外键引用错误 0。

随机 100 条边逐条比较 `ST_StartPoint(edge)` 与 source node、`ST_EndPoint(edge)` 与 target node，两个方向的最大几何误差均为 0 m。

弱连通分量 272 个，强连通分量 272 个；最大分量有 22,151 个节点，占 95.4990%。小分量是实际 OSM 步行图的一部分，没有为美化结果删除。

## 4. 步行成本与 connector

统一采用 4.8 km/h（1.3333 m/s、80 m/min）的静态步行速度假设：

```text
travel_time_s = length_m / (4.8 / 3.6)
```

居住点在 300 m 内吸附到 `pedestrian_nodes`。起点 connector 时间为 `origin_snap_distance_m / walking_speed_mps`，会从 300/600/900 秒预算中扣除。POI connector 同样按其 300 m 内步行节点映射距离计时。

因此 POI 总步行时间为：

```text
origin connector + pedestrian network agg_cost + POI connector
```

该模型不包含年龄、坡度、台阶减速、信号灯等待、天气或个人体力差异，也不代表实时个人步行时间。

## 5. POI Walk Access

`scripts/osm/build_poi_walk_access.py` 使用 geography `ST_DWithin` 和 KNN，把现有真实 POI 映射到 300 m 内的独立步行节点。重复执行两次均得到 2,303 行和相同 SHA-256，没有重复插入。

| 类别 | POI | mapped | unmapped | 平均 snap | 最大 snap |
| --- | ---: | ---: | ---: | ---: | ---: |
| commercial | 176 | 176 | 0 | 45.30 m | 155.60 m |
| healthcare | 102 | 102 | 0 | 43.03 m | 130.71 m |
| education | 378 | 377 | 1 | 69.74 m | 269.98 m |
| recreation | 176 | 176 | 0 | 62.11 m | 245.99 m |
| transport | 1,424 | 1,420 | 4 | 38.48 m | 239.86 m |
| emergency | 4 | 4 | 0 | 45.56 m | 92.15 m |
| public_safety | 48 | 48 | 0 | 35.90 m | 129.72 m |
| **合计** | **2,308** | **2,303** | **5** | **46.08 m** | **269.98 m** |

## 6. 15 分钟网络算法

每次请求只执行一次：

```sql
pgr_drivingDistance(
  'SELECT id, source, target, cost, reverse_cost FROM pedestrian_edges',
  :origin_node,
  900 - :origin_connector_time_s,
  directed => true
)
```

返回的网络累计成本加上起点 connector 后按 `<=300`、`<=600`、`<=900` 秒划分 5/10/15 分钟节点。POI 是否可达则另外加入 POI connector，只有总时间不超过阈值才计入。

POI 资格不使用 Polygon Contains。凹壳仅用于地图表达，河流、铁路、围墙、断路和绕行都可能使多边形内部的点在道路网络上不可达；正式资格完全依据网络总步行时间。统计基于全部真实可达核心 POI，地图显示按类别和时间取前 30 个，不改变统计结果。

## 7. Isochrone

可达 `pedestrian_nodes` 转换到 EPSG:32648，使用 `ST_Collect`、`ST_ConcaveHull`、`ST_MakeValid` 和 Polygon 提取，再转回 EPSG:4326；面积在 EPSG:32648 中计算。

中心点对 0.70、0.80、0.85、0.90 做了真实对比，所有结果均合法且为单一部分。最终固定 `target_percent=0.85`，中心 5/10/15 分钟原始面积分别为 0.0680、0.5420、1.5097 km²；它比 0.90 保留更多网络边界细节。父层按顺序 union 并使用 0.1 m 数值容差，保证 `ST_Covers(iso10, iso5)` 和 `ST_Covers(iso15, iso10)`。

少于 3 个节点或凸包退化时，对实际可达节点在 EPSG:32648 中使用 20 m buffer。东部边界案例只有 1 个节点，仍返回合法的 0.0013 km² 几何，没有 API 500。

## 8. 生活服务类别与覆盖语义

核心类别为 commercial（商业生活服务）、healthcare（医疗服务）、education（教育服务）、recreation（休闲活动）和 transport（交通服务）。`emergency` 与 `public_safety` 不进入核心覆盖指标。

服务类别覆盖率只表示“5 个核心类别中，至少存在 1 个 15 分钟网络可达 POI 的类别占比”。它没有主观权重，不是生活圈综合得分、官方规划达标率或居民满意度评价。

## 9. 十组真实案例

| 场景 | 起点 | snap / connector | 5/10/15 分钟节点 | 15分钟面积 | 可达 POI | 类别覆盖 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 中心城区 | 103.8343,36.0611 | 39.4 m / 29.5 s | 32 / 179 / 412 | 1.5102 km² | 46 | 5/5（1.0） |
| 七里河 | 103.7700,36.0600 | 15.7 m / 11.7 s | 19 / 56 / 119 | 1.0642 km² | 20 | 3/5（0.6） |
| 安宁 | 103.7200,36.1000 | 54.9 m / 41.1 s | 27 / 109 / 290 | 1.6476 km² | 24 | 4/5（0.8） |
| 东部 | 103.9300,36.0500 | 17.0 m / 12.7 s | 2 / 13 / 27 | 0.3346 km² | 1 | 1/5（0.2） |
| 西部 | 103.6500,36.0800 | 44.6 m / 33.4 s | 10 / 25 / 73 | 1.3374 km² | 3 | 1/5（0.2） |
| 南部边缘 | 103.8242,35.9932 | 21.2 m / 15.9 s | 1 / 2 / 16 | 0.1706 km² | 1 | 1/5（0.2） |
| 北部边缘 | 103.8325,36.1470 | 29.9 m / 22.4 s | 4 / 7 / 8 | 0.2437 km² | 0 | 0/5（0.0） |
| 东部边界 | 104.0595,36.0800 | 30.7 m / 23.0 s | 1 / 1 / 1 | 0.0013 km² | 0 | 0/5（0.0） |
| 西部边界 | 103.6100,36.0700 | 127.3 m / 95.5 s | 5 / 8 / 16 | 0.2264 km² | 0 | 0/5（0.0） |
| 东北边缘 | 104.0197,36.1485 | 18.5 m / 13.9 s | 2 / 3 / 8 | 0.2931 km² | 0 | 0/5（0.0） |

中心城区的 46 个可达核心 POI 分布为商业 4、医疗 2、教育 5、休闲 4、交通 31。其 5/5 覆盖只陈述设施类别存在情况，不作规划达标结论。

完整逐案数据见 `docs/phase-8-benchmark.json`。

## 10. 性能与 EXPLAIN

同一开发机预热后执行 10 个不同位置：

| 阶段 | 平均 | 最小 | 最大 |
| --- | ---: | ---: | ---: |
| 居住点吸附 | 1.544 ms | 0.953 ms | 3.222 ms |
| pgr_drivingDistance | 31.155 ms | 24.693 ms | 45.439 ms |
| POI 可达关联 | 1.647 ms | 1.306 ms | 2.040 ms |
| 几何构造 | 35.449 ms | 2.728 ms | 142.894 ms |
| API 总时间 | 74.546 ms | 36.395 ms | 196.498 ms |

`EXPLAIN (ANALYZE, BUFFERS)` 显示：起点吸附命中 `idx_pedestrian_nodes_geography`，执行 0.042 ms；单节点 POI 映射命中 `ix_poi_walk_access_node_id`，执行 0.017 ms；中心 `pgr_drivingDistance` 返回 449 行，执行 38.170 ms；可达 POI 关联总执行 36.975 ms。2,303 行映射表在多节点关联中采用小表顺序扫描与 hash join，符合当前规模的 planner 选择。

## 11. API 与错误语义

`POST /api/v1/living-circle/analyze` 接收 origin 和 `max_snap_m`，响应包含 origin、步行节点吸附、walking model、三层 GeoJSON Isochrone、summary、五类统计、地图显示 POI 和数据质量。

- 422：非法经纬度、非法 `max_snap_m` 或 300 m 内没有步行节点；
- 503：步行网络、POI 映射、数据库、pgRouting 或 Isochrone 不可用。

中心真实 HTTP 请求返回 snap 39.4 m、15 分钟 412 个节点、46 个 POI、5/5 类别覆盖和 1.5102 km²。

## 12. 自动化与浏览器验收

- 完整 pytest：138 passed，包含 Phase 0–7 的 112 项基线与 Phase 8 的 26 项新测试；仅有 1 个第三方 Starlette/anyio deprecation warning。
- `npm run build`：TypeScript 检查和 Vite 构建通过；主 chunk 大于 500 kB 的既有非阻断提示保留。
- PostgreSQL/PostGIS/pgRouting 容器 healthy；真实 HTTP 健康检查和生活圈请求通过。
- 浏览器验证居住点、吸附点、虚线 connector、三层步行圈、真实可达 POI、五类筛选、类别统计和 POI 弹窗。弹窗显示 POI 名称、类别/子类、总步行时间、网络时间与 POI connector。
- 五类筛选逐项关闭时只影响地图 POI，生活圈几何与完整统计保持不变；全部恢复后显示正常。
- 连续快速点击三个位置后只保留最后位置结果；再次点击、重新选择、清除和离开模块均清理或更新旧结果，AbortController 生效。
- Phase 3 空间查询、Phase 5 点到点/最近设施、Phase 6 机动车 Isochrone、Phase 7 医疗应急，以及 POI/道路/建筑基础图层均通过浏览器回归。
- Browser Console 无应用 error；有 1 条 OpenFreeMap 远程字体 glyph 范围 404 warning，MapLibre 已回退本地渲染对应符号，不影响业务请求或图层。

## 13. 已知限制

- 步行成本使用统一 4.8 km/h 静态速度，不含坡度、台阶减速、过街等待、天气和个人差异。
- OSM 路网与 POI 完整性取决于社区数据；5 个 POI 因距步行节点超过 300 m 未映射。
- 可达圈由可达顶点凹壳近似，没有对道路边上的精确时间截止位置插值。
- 研究区边缘和 272 个真实小连通分量会产生节点少、面积小或无可达 POI 的结果。
- 地图每个核心类别最多显示最近 30 个 POI，统计仍基于全部可达数据。
- 前端主 chunk 仍超过 500 kB；本阶段没有进行 Phase 9 的界面重构。
- 外部底图字体服务对一个符号范围返回 404，当前由 MapLibre 本地字体回退处理。
