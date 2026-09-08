# Phase 6 验证记录

验证日期：2026-09-08。

## 1. 目标与边界

Phase 6 在 Phase 4/5 的真实兰州有向道路网络上实现固定 5、10、15 分钟静态道路时间 Isochrone。正式可达性来自 PostgreSQL、PostGIS 和 pgRouting；没有使用欧氏圆、前端模拟或 NetworkX，也没有加入 POI 统计、实时交通或应急调度。

返回边界是“基于可达道路顶点生成的空间服务区近似边界”，不代表道路边上所有连续位置经过精确插值后的理论边界。

## 2. 节点吸附

复用 Phase 5 的 `snap_point_to_network`。输入点以 EPSG:4326 geography 进行 `ST_DWithin` 米制过滤，并按 geography KNN 与 node ID 稳定排序，默认最大吸附距离为 500 m。查询继续使用 `idx_road_nodes_geography` GiST 表达式索引；超距时返回 422，不强制选择远处节点。

中心点 `(103.8343,36.0611)` 吸附到 node `4077238566`，距离 208.2 m。10点实测吸附查询平均 2.107 ms、最小 2.020 ms、最大 2.237 ms。

## 3. pgr_drivingDistance 与有向语义

每次请求只运行一次：

```sql
pgr_drivingDistance(
  'SELECT id, source, target, cost, reverse_cost FROM routing_edges',
  :start_node,
  900,
  directed => true
)
```

数据库返回的 `agg_cost` 分别以 `<=300`、`<=600`、`<=900` 秒生成三个节点集合。`cost` 等于 Phase 4 建立的静态 `travel_time_s`，`reverse_cost=-1`，因此结果是静态道路时间范围，不是实时交通范围。

所有真实案例均满足 `nodes5 ⊆ nodes10 ⊆ nodes15` 以及 `count5 <= count10 <= count15`。

## 4. 几何算法

可达节点 geometry 从 EPSG:4326 转为兰州所在的 EPSG:32648，随后使用 `ST_Collect` 和 `ST_ConcaveHull(points, 0.85, false)` 构造原始服务区。0.85 是固定的 target percent；该值在真实研究区上保留道路网络的空间形态，同时避免极低参数带来的过细碎边界与额外计算。

所有结果经过 `ST_MakeValid` 和 `ST_CollectionExtract(..., 3)`，对外只返回 Polygon/MultiPolygon。面积使用 EPSG:32648 的 `ST_Area` 计算，再返回 `area_m2` 和 `area_km2`。

嵌套关系按顺序构造：10分钟几何与5分钟几何执行 `ST_UnaryUnion`，15分钟几何再与10分钟几何合并。父层额外使用固定 0.1 m 数值容差 buffer，避免坐标投影和 GeoJSON 序列化造成亚平方米级边界误差。真实 GeoJSON 回读后通过 `ST_Covers(iso10, iso5)` 和 `ST_Covers(iso15, iso10)`。

当可达节点少于3个或其凸包面积为0时，不调用凹壳，而对实际可达顶点集合应用固定 20 m buffer。测试选取无出边顶点得到1个可达节点，三个时段均返回合法且面积大于0的 MultiPolygon，没有 API 500。这个 fallback 只表达小连通分量顶点附近的最小可视范围。

## 5. API

`GET /api/v1/routing/isochrone?lon=...&lat=...&max_snap_m=500`

响应包含 origin、吸附 node 与距离、`static_travel_time` 成本模型、`directed: true`、最大900秒分析时间，以及含3个 Feature 的 GeoJSON FeatureCollection。每个 Feature 包含 minutes、threshold_s、reachable_node_count、area_m2 和 area_km2。

经纬度和 `max_snap_m` 由 FastAPI/Pydantic 校验；非法参数及超距吸附返回422，数据库、pgRouting或几何构造失败返回503。

## 6. 真实案例

| 位置 | 起点 | snap | 5分钟节点 / km² | 10分钟节点 / km² | 15分钟节点 / km² | API |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 西部边缘 | 103.6200,36.0700 | 112.5 m | 18 / 0.781 | 77 / 6.064 | 617 / 22.100 | 60.265 ms |
| 西部 | 103.6800,36.0900 | 269.0 m | 515 / 21.458 | 2,127 / 93.823 | 3,424 / 185.931 | 92.195 ms |
| 七里河西部 | 103.7200,36.0500 | 58.2 m | 181 / 9.622 | 1,111 / 39.059 | 2,717 / 128.203 | 208.211 ms |
| 七里河 | 103.7800,36.0600 | 96.2 m | 791 / 21.087 | 2,718 / 106.716 | 4,999 / 239.922 | 128.051 ms |
| 中心城区 | 103.8343,36.0611 | 208.2 m | 1,001 / 18.544 | 3,079 / 77.578 | 4,556 / 206.719 | 118.179 ms |
| 城关东部 | 103.8800,36.0600 | 79.0 m | 891 / 16.219 | 2,381 / 60.119 | 3,633 / 173.097 | 97.963 ms |
| 东部 | 103.9300,36.0500 | 90.3 m | 125 / 7.647 | 1,047 / 65.938 | 2,590 / 155.600 | 157.145 ms |
| 东部边缘 | 104.0000,36.0600 | 178.5 m | 30 / 2.477 | 113 / 18.890 | 398 / 65.941 | 72.398 ms |
| 西北边缘 | 103.7500,36.1300 | 351.3 m | 62 / 1.974 | 172 / 11.543 | 858 / 38.636 | 183.479 ms |
| 东北边缘 | 103.9100,36.1200 | 92.6 m | 87 / 3.022 | 170 / 8.670 | 971 / 50.549 | 183.159 ms |

面积差异反映有向路网连通性、道路速度和研究区边缘，不是按时间平方生成的固定圆。

## 7. 单向道路验证

继续使用南滨河东路 OSM Way `420345709`、routing edge `13266`，方向为 `6528742291 → 6528742285`，cost 0.1591 s、reverse_cost -1。以 source 执行 `pgr_drivingDistance(... directed => true)` 时，target 由 edge 13266 到达；以 target 反向执行时，source 由 edge 488 绕行到达，累计 2.5161 s，没有把 edge 13266 当作反向边。

## 8. 性能

本机预热后测试10个不同位置。geometry 是完整数据库查询时间减去独立 driving-distance 查询时间，用于近似分离几何开销；database total 和 API total 是直接计时。

| 阶段 | 平均 | 最小 | 最大 |
| --- | ---: | ---: | ---: |
| 节点吸附 | 2.107 ms | 2.020 ms | 2.237 ms |
| pgr_drivingDistance | 34.370 ms | 13.387 ms | 55.731 ms |
| 几何处理 | 93.020 ms | 34.628 ms | 194.395 ms |
| 数据库核心查询 | 127.389 ms | 51.375 ms | 231.370 ms |
| API总时间 | 130.105 ms | 60.265 ms | 208.211 ms |

可重复脚本为 `scripts/validation/phase6_benchmark.py`，逐点结果、完整执行计划和数据库版本保存在 `docs/phase-6-benchmark.json`。

## 9. EXPLAIN (ANALYZE, BUFFERS)

中心点吸附继续使用 `idx_road_nodes_geography` Index Scan，shared buffer hit 35，Execution Time 0.135 ms。

中心 Isochrone 核心计划中 `pgr_drivingDistance` Function Scan 返回4,556个900秒可达节点；路网有8,286个节点、18,441条有向边。核心 SQL shared buffer hit 1,012，Execution Time 105.472 ms。pgRouting读取当前规模的完整 edges SQL，未通过修改 planner 或错误索引化改变算法。

## 10. 自动化测试

- 完整 pytest：89 passed，1个第三方 Starlette/anyio deprecation warning。
- Phase 6 新增17项集成测试，覆盖 API、参数、超距、503、单次900秒有向 driving distance、集合包含、几何合法性/SRID/覆盖、面积、退化 fallback 和真实单向边。
- `npm run build`：TypeScript 与 Vite 构建通过；保留主 chunk 大于500 kB的非阻断提示。
- PostgreSQL 16.4、PostGIS 3.4.3、pgRouting 3.8.0 容器保持 healthy，未清理 named volume。

## 11. 浏览器验收

在真实 Codex IAB 浏览器完成：

- API Online、PostGIS Connected。
- 中心点击 `(103.83396,36.06123)` 后显示三层半透明范围，面板为1,001/3,079/4,556节点及18.544/77.578/206.719 km²，与 API 一致。
- 15分钟蓝色大范围先绘制、10分钟绿色居中、5分钟橙色最上层，轮廓清楚且起点、吸附点和虚线可见。
- 第二次点击 `(103.79242,36.04652)` 后，旧范围更新为79/976/3,139节点及2.526/32.497/119.831 km²。
- 实测超距点显示500米内无法吸附的业务提示，没有进入通用500错误。
- 快速连续点击后最终只保留最后点 `(103.91258,36.04930)` 的结果：374/1,436/2,872节点及8.757/55.921/141.326 km²；旧请求未覆盖最终状态。
- 清除结果后3个面图层完全移除；重新选择与模式切换正常。
- 点到点回归得到6.02 km、8.11 min、32 edges；医院和消防查询均返回真实路径与候选设施。
- Phase 3空间查询返回附近POI 86、相交建筑909、范围内建筑占地752,561 m²。
- POI层加载2,307条；高缩放下道路层加载2,412条、建筑层加载4,961条。
- Browser Console 只有 Vite连接、React开发提示，没有 error 或 warning。

## 12. 已知限制

- 97.67%的道路速度来自 highway 类别默认值，时间不代表实时交通或实时 ETA。
- 输入点采用 vertex snapping；输入点到吸附顶点的距离不计入可达时间。
- 服务区来自可达道路节点凹壳，是顶点近似边界，没有对道路边上的连续截止位置插值。
- 研究区边界和小连通分量会使边缘结果出现较少节点或不规则范围；退化结果会明确使用20 m顶点 buffer。
- 0.1 m父层容差只用于抵消投影/序列化造成的数值拓扑误差。
- Vite主 chunk仍超过500 kB，本阶段未进行大规模前端拆分。
