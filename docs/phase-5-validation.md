# Phase 5 验证记录

验证日期：2026-09-08。

## 1. 目标与边界

Phase 5 在 Phase 4 的真实兰州有向道路网络上实现“最短估计通行时间路径”和“按网络时间选择最近设施”。本阶段没有实现 Isochrone、`pgr_drivingDistance` 业务接口、实时交通、应急调度或 15 分钟生活圈。

## 2. Vertex snapping 设计

地图点通过 PostGIS 吸附到最近的 `road_nodes` 顶点。查询先用 `ST_DWithin(geometry::geography, point::geography, max_snap_m)` 限制候选，再按 geography KNN 距离与 node ID 确定性排序。默认上限为 500 m，API 允许 100–1,000 m；范围内无节点返回 422 业务错误，不选择远处节点。

选择 road-node snapping 是为了在现有拓扑上使用稳定且可验证的顶点路由。本实现是 vertex snapping，不宣称完整 map matching 或 edge-position snapping。响应返回 node ID、节点坐标和米制 `snap_distance_m`。地图中的虚线只表示输入点与吸附节点的关系，不计入道路距离或通行时间。

`005_phase5_routing.sql` 增加 `idx_road_nodes_geography` 表达式 GiST 索引。中心点吸附的 `EXPLAIN (ANALYZE, BUFFERS)` 使用该 Index Scan，返回 25 个半径候选后取最近点；执行时间 0.112 ms、shared buffer hit 35，未修改 planner 参数。

## 3. Dijkstra 与有向图语义

正式路径使用 pgRouting 3.8 的 `pgr_dijkstra`，候选设施成本使用一次 one-to-many `pgr_dijkstraCost`。固定 edges SQL 为：

```sql
SELECT id, source, target, cost, reverse_cost FROM routing_edges
```

所有调用都使用 `directed => true`。`cost=travel_time_s`，全部 `reverse_cost=-1`；反向通行只能使用数据库中另一条合法显式有向边。前端和请求均不能提交 edges SQL、表名或列名。

路由结果按 `path_seq` 关联 `routing_edges`，直接拼接每条真实道路 geometry。服务逐边验证 `edge[i].target = edge[i+1].source`，同时要求相邻 geometry 端点完全衔接。道路距离与时间分别由数据库边的 `length_m` 和 `cost` 求和；同一吸附节点返回距离 0、时间 0、edge count 0 的有效零路网路径。

## 4. 实际点到点案例

| 起点 → 终点 | 起/终点吸附 | 道路距离 | 预计时间 | 边数 | API |
| --- | ---: | ---: | ---: | ---: | ---: |
| `(103.8343,36.0611)` → `(103.8500,36.0700)` | 208.2 / 179.0 m | 2,515.4 m | 210.6 s | 14 | 16.85 ms |
| `(103.7200,36.0500)` → `(103.7800,36.0600)` | 58.2 / 96.2 m | 6,800.3 m | 565.8 s | 29 | 17.83 ms |
| `(103.7800,36.0600)` → `(103.9000,36.0800)` | 96.2 / 159.7 m | 14,316.3 m | 1,050.1 s | 60 | 约 18 ms |

集成测试另取最大强连通分量的 20 条成功路径，逐条验证 topology、geometry、`SUM(cost)`、`SUM(length_m)`，没有发现断裂或重复正成本自环。

## 5. 单向道路与自环

真实样本为南滨河东路 OSM way `420345709`、routing edge `13266`，方向 `6528742291 → 6528742285`。正向路径使用该 edge；反向查询没有非法使用 edge 13266，而是使用 3 条合法 edge 绕行 25.6 m、2.5 s。数据库约束测试确认 18,441 条 routing edge 的 `reverse_cost` 全为 -1。

保留 Phase 4 的 39 条真实闭合道路自环。20 条成功路径没有选择增加成本的自环，也没有出现重复自环造成的异常成本。

## 6. 设施路网映射

新增 `poi_routing_access(poi_id, node_id, snap_distance_m, created_at)`。`poi_id` 是指向 `pois.id` 的唯一主键，`node_id` 指向 `road_nodes.osm_node_id` 并有 B-tree 索引；snap 距离有 0–500 m 检查约束。

映射只使用真实 OSM `healthcare` 和 `emergency` POI，并由 PostGIS LATERAL 查询为每个 POI 选择 500 m 内最近道路节点。

| 类别 | POI | 已映射 | 超距/未映射 | 平均 snap | 最大 snap |
| --- | ---: | ---: | ---: | ---: | ---: |
| healthcare | 102 | 102 | 0 | 99.44 m | 429.32 m |
| emergency | 4 | 4 | 0 | 120.67 m | 149.27 m |
| 合计 | 106 | 106 | 0 | — | 429.32 m |

细分类为 hospital 58、clinic 23、doctors 21、fire_station 4。构建脚本连续执行两次，均得到 106 行，排序映射 SHA-256 均为 `6c3e3d35c64c518c0ea159e2416e82fe17f961e5b019eedcd58a080ee24cd949`，没有重复增长或映射漂移。

实际映射 SQL 的 EXPLAIN 对 58 家医院执行 Nested Loop，并在每次 LATERAL 顶点查找中使用 `idx_road_nodes_geography`；总执行时间 4.388 ms。完整执行计划保存在 `phase-5-benchmark.json`。

## 7. 最近设施算法与案例

起点先做一次顶点吸附；设施目标节点去重后，一次 `pgr_dijkstraCost` 计算一对多成本；不可达设施被过滤；结果按网络时间、设施 snap、直线距离、POI ID 稳定排序；只为返回的最佳节点集合恢复路径，第一名路线返回给地图。同一节点上的多个 POI 不会丢失。

三组医院：

| 起点 | 网络最优医院 | 直线距离 | 网络距离 | 预计时间 | 设施 snap |
| --- | --- | ---: | ---: | ---: | ---: |
| `(103.7200,36.0500)` | 兰州第三医院 | 1,570.6 m | 2,498.9 m | 270.9 s | 129.7 m |
| `(103.7800,36.0600)` | 甘肃省妇幼保健院 | 1,271.7 m | 2,292.9 m | 194.6 s | 81.3 m |
| `(103.8343,36.0611)` | 甘肃玛利亚妇科医院 | 679.4 m | 1,013.7 m | 88.7 s | 62.5 m |

三组消防站：

| 起点 | 网络最优消防站 | 直线距离 | 网络距离 | 预计时间 | 设施 snap |
| --- | --- | ---: | ---: | ---: | ---: |
| `(103.7200,36.0500)` | 未命名 OSM 消防站（POI 45） | 391.2 m | 530.2 m | 67.0 s | 92.2 m |
| `(103.7800,36.0600)` | 七里河消防队 | 1,786.4 m | 3,133.3 m | 241.1 s | 110.4 m |
| `(103.8343,36.0611)` | 七里河消防队 | 6,116.5 m | 7,392.8 m | 511.9 s | 110.4 m |

中心真实案例清楚显示直线最近与网络时间最优不同：医院中，兰州市第一人民医院城关医院直线 646.1 m、网络时间 98.9 s，而网络第一名甘肃玛利亚妇科医院直线 679.4 m、网络时间 88.7 s；消防站中，兰州市南北两山消防中队直线 5,873.5 m、网络时间 547.4 s，而七里河消防队直线 6,116.5 m、网络时间 511.9 s。数据和道路 cost 均未为此案例修改。

中心起点可达医院 57/58、消防站 3/4，各有 1 个设施位于不可达的有向网络部分。接口正常过滤并在 metadata 中报告，不返回 500。

## 8. API 与错误处理

- `POST /api/v1/routing/shortest-path`：接收 start/end 与可选 max snap，返回两端吸附信息、真实 LineString 和路线统计。
- `GET /api/v1/routing/nearest-facility`：接收 origin、healthcare/emergency、可选细类、max snap 和 1–10 limit，返回网络第一名、3–5 个候选、第一名路线和可达性统计。

经纬度、category、subcategory、limit 和 max snap 由 Pydantic/FastAPI 验证；超距吸附返回 422，无路径、无匹配设施或全部不可达返回 404，数据库或路径几何异常返回 503。不同弱连通分量的实际请求返回 404 `No routable path between snapped nodes`。

## 9. 性能

本机预热后实测；snap 为直接 PostGIS 顶点吸附，routing 为 pgRouting 与 geometry 恢复，API 包含 FastAPI/TestClient 序列化开销。单位均为 ms。

| 组别 | snap 平均/中位/最大 | routing 平均/中位/最大 | API 平均/中位/最大 |
| --- | ---: | ---: | ---: |
| 点到点 10 组 | 2.97 / 2.59 / 6.52 | 12.18 / 11.91 / 15.19 | 19.12 / 18.69 / 27.39 |
| hospital 5 组 | 1.98 / 2.03 / 2.07 | 23.15 / 22.61 / 24.65 | 29.87 / 30.28 / 31.07 |
| fire_station 5 组 | 1.79 / 1.79 / 1.85 | 23.18 / 23.10 / 27.70 | 30.94 / 30.82 / 34.91 |

可重复基准脚本为 `scripts/validation/phase5_benchmark.py`，原始案例、每次时序、映射哈希和完整 EXPLAIN 在 `docs/phase-5-benchmark.json`。

## 10. 前端实现

“路径规划”是独立模块，含“点到点”和“最近设施”模式。地图区分用户起点、终点、吸附节点、橙色真实道路路线、灰色吸附虚线、最佳设施与其他候选。面板显示道路距离、静态预计时间、edge count、起终点 snap；最近设施还显示类型、直线/网络距离、设施 snap、可达统计和前 3–5 名。路线与候选设施支持 Popup。

每次点位、模式或设施类型变化都会由 React effect 创建新的 `AbortController`，依赖变化会取消上一请求，旧响应不能覆盖最后操作。状态覆盖 idle、selecting_start、selecting_end、loading、success、no_route、snap_failed、empty_facilities、error。

## 11. 自动化测试

- 完整 pytest：72 passed，1 个第三方 Starlette/anyio deprecation warning。
- 新增 30 项 Phase 5 集成用例；直接连接真实 PostGIS/pgRouting，没有 mock 路由函数。
- `npm run build`：TypeScript 与 Vite 构建通过；保留既有主 chunk 超过 500 kB 的非阻塞 warning。
- 数据库迁移、映射两次执行、哈希、EXPLAIN、10+5+5 性能测试均通过。

## 12. 浏览器验收

在真实 Codex IAB 浏览器中完成：

- 点到点：点击 `(103.78349,36.05846)` 与 `(103.81782,36.07095)` 后显示沿道路转折的橙色路线；面板为 6.27 km、8.26 min、36 edges、起/终点 snap 48/164 m。路线 Popup 同步显示距离、时间与 edge count。
- 路线控制：清除路线会移除结果，重新选择会清空点位并回到 selecting_start。
- 医院：点击 `(103.80924,36.05846)` 后，网络第一名为兰州中研白癜风医院，路线 496 m、1.20 min，返回 5 个候选；metadata 为已映射 58、可达 57、不可达 1。
- 消防站：同一浏览器会话切换类型后，网络第一名为七里河消防队；一组结果为 3,157 m、4.30 min、18 edges，返回全部 3 个可达候选并报告 1 个不可达设施。
- 快速点击：连续三次更换起点，最终面板只保留最后坐标 `(103.77969,36.06141)` 及其七里河消防队结果，旧请求未覆盖最终状态。
- 地图结果：实际看到道路路线、起点、吸附节点、最佳设施与其他候选的不同样式；没有用输入点至设施的直线冒充道路路线。
- 浏览器会话中页面关键 Error 为 0；MapLibre 加载和 API 请求均未进入 error 状态。既有底图缺失少量 sprite 的非关键 warning 不影响业务图层。

## 13. Phase 1–4 回归

自动化套件确认健康检查、PostGIS、POI/建筑 GeoJSON、空间查询、路网 API/stats 及 Phase 4 方向约束没有回归。浏览器再次确认 API Online、PostGIS Connected、WGS84 坐标与返回兰州；POI 载入 2,307 条；高缩放视窗载入 61 条道路和 167 个建筑；1 km 空间查询返回附近 POI 91、相交建筑 977、范围内建筑占地 804,602 m²，并正确绘制查询圈与分类点。

## 14. 已知问题

- 97.67% 道路使用 highway 类别默认静态速度，因此时间是静态估算，不是实时 ETA。
- vertex snapping 可能把点吸附到道路交叉口附近的顶点；输入点到节点的虚线距离不计入路径成本。
- 研究区存在 70 个弱连通分量；设施可因道路方向或分量而不可达，接口会过滤并报告。
- OSM 设施覆盖与命名取决于社区数据；4 个消防站中有 1 个无名称。
- Vite 主 chunk 仍超过 500 kB；该 warning 不影响 Phase 5 功能。
