# Phase 4 验证记录

验证日期：2026-09-08。

## 1. Phase 4 目标

将 Phase 2 的真实 OSMnx drive `MultiDiGraph` 转换为下一阶段可直接使用的有向、pgRouting-ready 路网，并提供只读调试 API 与 MapLibre 视窗图层。本阶段没有实现 Dijkstra、A*、最短路径、最近设施或 Isochrone。

## 2. 原始 road_nodes / road_edges 结构

- `road_nodes`：8,286 行，主键 `osm_node_id bigint`，`POINT` EPSG:4326。
- `road_edges`：18,441 行，字段为 `id, u, v, edge_key, osm_id, name, highway, oneway, maxspeed, length_m, geometry`。
- `u` 是有向边起点 OSM node，`v` 是终点；`(u, v, edge_key)` 保持 OSMnx 多重边唯一性。
- 原始 GraphML 共有 430 条边提供 `maxspeed`，1,529 条边提供 `lanes`。Phase 4 保留路由所需的 `maxspeed`；`lanes` 暂不参与 cost。

## 3. routing schema 设计

新增 `routing_edges`，保留 `road_edges` 的原始数据层语义。每条 routing edge 通过唯一 `road_edge_id` 外键追溯至原始 OSM edge，同时复制查询与算法所需字段，避免 Phase 5 反复 join 大表。路由节点直接复用稳定 OSM node ID，无需创建随机的 `routing_vertices`。

主要字段：`id, road_edge_id, source, target, osm_id, edge_key, name, highway, oneway, maxspeed, speed_kph, speed_source, length_m, travel_time_s, cost, reverse_cost, geometry`。

## 4. pgRouting 安装方式

`database/Dockerfile` 使用锁定 digest 的 `postgis/postgis:16-3.4`，并安装固定包版本 `postgresql-16-pgrouting=3.8.0-1.pgdg110+1`。Compose 使用项目镜像 `cityscope/postgis-pgrouting:16-3.4`。已有 named volume 在容器重建过程中保留，未执行 `docker compose down -v`。

实测版本：PostgreSQL 16.4、PostGIS 3.4.3、pgRouting 3.8.0。`SELECT pgr_version()` 返回 `3.8.0`。

## 5. source / target 生成逻辑

`source = road_edges.u`，`target = road_edges.v`，并分别以外键指向 `road_nodes.osm_node_id`。18,441 条边的 source/target 均非空且都能映射到真实节点。未执行几何近似 snap。

## 6. 单向道路处理

OSMnx 已按 `network_type="drive"` 生成有向 MultiDiGraph，因此 ETL 不再用字符串覆盖方向。18,441 条有向边中，`oneway=true` 为 3,745 条，`oneway=false` 为 14,696 条；14,726 条记录存在显式反向边，其中 30 条标记为单向但存在由 OSM 数据中另一条合法 edge 提供的反向连接。

每行只允许 `source → target`，`cost = travel_time_s`，所有 `reverse_cost = -1`。双向道路依靠 OSMnx 已生成的反向行通行，避免“显式双边 + 正 reverse_cost”重复建模。

## 7. 多重边处理

仅按 `(u, v, edge_key)` 去重。真实案例 `u=9912997909, v=9912997912` 有 key `0,1,2`，原始 edge id `15998,15999,16000`；三条均进入 routing 表。反向 `9912997912 → 9912997909` 同样保留三个 key。routing 与 raw edge 总数均为 18,441。

## 8. length_m 算法

复用 OSMnx 已提供、单位为米的 `length` 并统一命名为 `length_m`。100 条随机抽样与 `ST_Length(geometry::geography)` 比较：平均绝对差 0.314 m，最大绝对差 3.615 m；平均相对差 0.1503%，最大 0.2276%。差异来自 OSMnx 对折线分段长度的测地计算方式，不建立第二套长度字段。

## 9. speed_kph 算法

优先解析 OSM `maxspeed`；缺失或异常时按 highway 类别应用静态默认值。组合 highway 取其中最低默认速度，防止过度乐观；无法识别的类别回退至 25 km/h。

## 10. maxspeed 解析

解析器支持数字、`km/h`、`mph`、分号值以及 GraphML 中的 list 字符串；mph 乘 1.609344。多个有效值取最小值，只接受 5–120 km/h。当前 430 条 OSM 值全部成功解析，覆盖率 2.3318%。

## 11. 默认速度映射

| highway | km/h |
| --- | ---: |
| motorway | 80 |
| trunk | 60 |
| primary | 50 |
| secondary | 40 |
| tertiary | 35 |
| residential | 30 |
| unclassified | 25 |
| living_street | 15 |
| service | 20 |
| motorway_link / trunk_link | 50 / 40 |
| primary_link / secondary_link / tertiary_link | 35 / 30 / 25 |
| busway / escape / fallback | 30 / 20 / 25 |

18,011 条使用默认值，占 97.6682%。全网边加权平均 `speed_kph=33.0787`。这些值是静态道路网络估计速度，不代表真实车速、实时交通速度或真实响应速度。

## 12. travel_time_s

公式为 `length_m / (speed_kph / 3.6)`，单位秒。分布：最小 0.114、P50 14.353、平均 27.845、P95 91.134、最大 1,066.626 秒；非正值为 0。

## 13. cost / reverse_cost

`cost=travel_time_s>0`；`reverse_cost=-1` 表示该行不隐含反向通行。需要反向通行时使用数据库中的另一条有向 edge。该约定可直接供 Phase 5 的 directed pgRouting 查询使用。

## 14. 索引

- `idx_routing_edges_geometry`：geometry GiST。
- `ix_routing_edges_source`、`ix_routing_edges_target`：拓扑 B-tree。
- `ix_routing_edges_highway`：筛选 B-tree。
- 主键 id 与唯一 road_edge_id 由唯一 B-tree 支持。

## 15. 连通性分析

通过 pgRouting `pgr_connectedComponents` 与 `pgr_strongComponents` 分析全部边，不运行路径业务算法。

- 节点：8,286；边：18,441；有向边长度合计 4,676.345 km。
- 弱连通分量：70；强连通分量：176。
- 最大弱连通分量：8,080 节点、18,095 边，占全部节点 97.5139%。
- 第二大分量 23 节点，之后两个分量各 15 节点；没有提前删除小分量。
- 孤立节点：0；按不同相邻节点计算的度为 1 节点：2,085。

仅 20 个度为 1 节点位于研究 bbox 边界 100 m 内。其余包含真实尽端路、小区/停车场内部路和局部孤立路段，不能一律视为错误。下载使用 `truncate_by_edge=True`，边可稍微延伸出 bbox，主分量范围约为 103.5914–104.0865、35.9734–36.1680。

## 16. 异常节点/边

NULL source 0、NULL target 0、空/无效 geometry 0、错误 SRID 0、`length_m<=0` 0、`speed_kph<=0` 0、`travel_time_s<=0` 0、非法 cost 0。存在 39 条 `source=target` 的真实自环；抽查显示其 geometry 均为闭合 ring，如小区闭合环路，因此保留并记录。

## 17. 拓扑端点验证

随机抽样 100 条 edge，以 geography 米制距离比较 edge 起终点与 source/target node：起点平均/最大误差均 0 m，终点平均/最大误差均 0 m。拓扑编号与几何端点精确一致。

## 18. network API

- `GET /api/v1/network/edges`：必须提供 bbox，面积不得超过 0.01 平方度；支持 highway 和 1–3,000 limit；在 PostGIS 内用 `&&`、`ST_Intersects`、`ST_MakeEnvelope` 查询，返回标准 GeoJSON。
- `GET /api/v1/network/stats`：返回节点/边、方向、长度、平均速度、弱/强连通分量、最大分量、孤立/度 1 节点、highway 与速度来源统计。

三类预热后各测 5 次的中位值：中心 z15 小视窗 183 edge / 9.69 ms / 93.1 KiB；西部稀疏区 z14 中视窗 288 / 12.55 ms / 145.1 KiB；东南边缘 z13 大视窗 571 / 22.30 ms / 324.1 KiB。

## 19. EXPLAIN

中心 bbox 查询计划使用 `Bitmap Index Scan on idx_routing_edges_geometry` 后接 `Bitmap Heap Scan`，候选 747、返回 745、移除 2，execution time 0.701 ms，shared buffer hit 108。没有强制 planner。

## 20. pytest

完整结果：42 passed，1 个第三方 anyio deprecation warning。Phase 4 新增真实数据库集成测试，覆盖扩展、完整性、方向规则、速度来源、多重边、索引、端点、bbox/highway/limit/错误输入、空结果与 stats。

## 21. 浏览器验收

真实 IAB 浏览器验证：API Online、PostGIS Connected；道路开关默认关闭；zoom 13+ 加载当前视窗；一次实测加载 940 条并显示道路；快速连续平移后最终计数更新为当前视窗 274 条，旧请求未覆盖；道路 Popup 显示 unclassified、442.4 m、25 km/h default、63.7 s、单向、source/target、OSM ID/key。Console JavaScript error 为 0。

## 22. Phase 1–3 回归

基础兰州底图、返回兰州、WGS84 坐标、POI 2,307 条前端载入、建筑 zoom 14+ 视窗载入（实测 1,781 条）、API/PostGIS 状态均正常。空间查询实测中心 `(103.837471,36.061235)`：1 km 内 POI 70、相交建筑 717、圈内占地 626,796 m²；医疗筛选返回 3 条。连续三次点击以后只显示最终中心及对应统计，请求取消正常。

## 23. 已知问题

- OSM maxspeed 覆盖率只有 2.33%，绝大多数 travel time 依赖静态类别速度。
- 研究 bbox 与 OSM 社区数据天然产生尽端、小连通分量及 39 条合法自环；Phase 5 应明确是否限制主分量，但本阶段保留全部真实边。
- MapLibre/OpenFreeMap 底图缺少 `office`、`sports_centre` 两个 sprite 时产生 2 条非关键 warning；业务图层与功能没有报错。
- Vite 产物主 chunk 约 1.24 MB，构建提示可在后续阶段拆包。

## ETL 幂等性

连续执行两次 `prepare_lanzhou.py --replace` 后，节点/边/长度/平均速度/OSM 速度数/单向边数完全一致，routing 关键字段排序哈希均为 `8424f2e8a6f3b72df4ae1fb81363bbb0`，没有数据翻倍。
