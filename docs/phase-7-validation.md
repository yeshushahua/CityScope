# Phase 7 验证记录

验证日期：2026-09-08。

## 1. 业务定义与边界

Phase 7 实现城市应急响应决策支持演示：用户选择医疗或消防事件、在地图设置事件位置，系统把事件点吸附到道路节点，从真实设施中计算预计响应时间，推荐最快可达设施，绘制该设施到事件点的完整路线，并展示该设施向外行驶 5/10/15 分钟的静态道路时间响应服务范围。

当前结果只使用静态道路速度、有向路网和 OSM 设施数据。它是 decision-support demonstration，不是实时急救或消防调度系统，也不代表真实出警时间。

## 2. 设施筛选

设施来自现有 `pois` 与 `poi_routing_access`，没有新增假设施或事件数据库表，也没有新增 migration。

- 医疗事件：`category='healthcare' AND subcategory='hospital'`。真实数据有 58 家医院，58 家已有道路节点映射；未把 clinic、doctors 无条件纳入应急医疗响应源。
- 消防事件：`category='emergency' AND subcategory='fire_station'`。真实数据有 4 个消防站，4 个已有道路节点映射。

中心城区真实计算中，58 家医院有 57 家可从设施节点到达事件节点、1 家不可达；4 个消防站有 3 个可达、1 个不可达。不可达设施直接排除，不以极大虚拟成本参与排序。

## 3. 设施到事件的有向响应算法

事件点继续复用 Phase 5/6 的 geography vertex snapping：`ST_DWithin` 限制 500 m，geography KNN 与 node ID 负责稳定选择，并使用 `idx_road_nodes_geography`。

候选响应时间由一次 many sources → one target 查询完成：

```sql
SELECT start_vid, end_vid, agg_cost
FROM pgr_dijkstraCost(
  'SELECT id, source, target, cost, reverse_cost FROM routing_edges',
  :facility_nodes,
  :incident_node,
  directed => true
)
```

候选设施按 `agg_cost`、设施吸附距离、直线距离和 POI ID 稳定排序。推荐设施是所有可达设施中静态道路时间最短者；直线距离只用于解释。选出推荐设施后，再运行一次 `pgr_dijkstra(recommended_facility_node, incident_node, directed => true)` 取得真实 `routing_edges` 几何、道路距离、时间、道路边数和 edge IDs。

这一方向与 Phase 5 的“事件点 → 设施”含义不同。在有向路网中 A→B 与 B→A 不保证同成本，因此 Phase 7 没有改名复用 Phase 5 的排序结果。

## 4. API 与错误语义

`POST /api/v1/emergency/response`

请求包含 incident、`medical|fire`、`max_snap_m`（100–1000，默认 500）和 `candidate_limit`（1–10，默认 3）。响应包含事件与吸附节点、设施总数/映射/可达/不可达统计、Top N 候选、推荐设施、设施→事件完整路线、响应 Isochrone、直线最近比较和模型元数据。

- 422：非法经纬度、类型或参数，以及事件点在最大距离内无法吸附。
- 404：没有匹配/映射设施，或全部设施无法到达事件节点。
- 503：数据库、pgRouting、完整路线或 Isochrone 构造失败。

## 5. 响应服务范围

Isochrone 直接复用 Phase 6 抽出的 `build_isochrones_from_node`，origin 是推荐设施道路节点，不是事件节点。只运行一次 900 秒 `pgr_drivingDistance(... directed => true)`，再按 300/600/900 秒生成 5/10/15 分钟可达顶点近似边界。普通 Phase 6 模式与应急模式共用原有 source 和 layer IDs，切换时更新数据与可见性，没有复制冲突图层。

## 6. 十组真实业务案例

下表为预热后的真实 API 结果；消防西部案例的推荐设施在 OSM 中没有名称，因此如实显示“未命名设施”。

| 场景 | 事件点 | snap | 推荐设施 | 距离 | 响应时间 | 直线最近=网络最优 | API |
| --- | --- | ---: | --- | ---: | ---: | --- | ---: |
| 医疗·中心 | 103.8343,36.0611 | 208.2 m | 兰州市第一人民医院城关医院 | 460.5 m | 44.8 s | 是 | 152.448 ms |
| 医疗·七里河 | 103.7800,36.0600 | 96.2 m | 七里河区中药医院 | 2,306.1 m | 176.7 s | 否 | 150.880 ms |
| 医疗·西部 | 103.6800,36.0900 | 269.0 m | 兰州安新大医院 | 2,904.2 m | 234.2 s | 否 | 112.214 ms |
| 医疗·东部 | 103.9300,36.0500 | 90.3 m | 兰州大学第一医院 | 2,178.3 m | 213.4 s | 是 | 123.642 ms |
| 医疗·北部边缘 | 103.7500,36.1300 | 351.3 m | 安宁区人民医院 | 5,146.4 m | 624.3 s | 否 | 138.567 ms |
| 消防·中心 | 103.8343,36.0611 | 208.2 m | 七里河消防队 | 6,966.3 m | 519.7 s | 否 | 140.386 ms |
| 消防·七里河 | 103.7800,36.0600 | 96.2 m | 七里河消防队 | 3,547.9 m | 266.7 s | 是 | 134.235 ms |
| 消防·西部 | 103.6800,36.0900 | 269.0 m | 未命名消防设施（POI 45） | 7,615.9 m | 612.9 s | 是 | 108.732 ms |
| 消防·东部 | 103.9300,36.0500 | 90.3 m | 七里河消防队 | 16,853.8 m | 1,292.5 s | 否 | 136.623 ms |
| 消防·北部边缘 | 103.7500,36.1300 | 351.3 m | 七里河消防队 | 8,565.8 m | 932.6 s | 否 | 156.787 ms |

完整 Top 3 候选、设施统计、5/10/15 分钟节点与面积保存在 `docs/phase-7-benchmark.json`。

## 7. 直线最近与网络时间最优

10 个案例中有 6 个真实差异：医疗七里河（直线 POI 1086、网络 POI 1022）、医疗西部（1978、1828）、医疗北部边缘（1947、2017）、消防中心（995、2025）、消防东部（995、2025）和消防北部边缘（2267、2025）。前端只在出现差异时显示“道路时间最优设施并非直线距离最近设施”。

## 8. Phase 5 与 Phase 7 方向差异

真实方向对比显示：

- 医疗中心：Phase 7 推荐 POI 1229，设施→事件 44.8 s；Phase 5 事件→设施推荐 POI 1031，88.7 s。
- 医疗七里河：Phase 7 推荐 POI 1022，176.7 s；Phase 5 推荐 POI 1138，194.6 s。
- 医疗北部边缘：Phase 7 推荐 POI 2017，624.3 s；Phase 5 推荐 POI 1955，622.0 s。
- 即使最佳设施 ID 相同，其他 7 个案例的两个方向成本也不同。例如消防中心设施→事件为 519.7 s，事件→设施为 511.9 s。

这说明响应方向会改变时间，并可能改变推荐设施。

## 9. 真实单向道路验证

重新验证 OSM Way `420345709`、routing edge `13266`：`6528742291 → 6528742285`，cost 0.15915 s，`reverse_cost=-1`。正向 `pgr_dijkstra` 使用 edge 13266；反向路径没有使用该禁止反向通行的 edge，而是以 3 条边绕行。Phase 7 的候选成本、最佳路线和服务范围均设置 `directed=true`。

## 10. 性能

同一台开发机预热后执行 5 个医疗和 5 个消防请求。内部阶段分别直接计时；API 总时间包含验证、数据库查询、GeoJSON 构造和序列化。

| 阶段 | 平均 | 最小 | 最大 |
| --- | ---: | ---: | ---: |
| 事件节点吸附 | 2.165 ms | 1.959 ms | 2.381 ms |
| 设施读取 | 1.900 ms | 1.610 ms | 2.190 ms |
| many-to-one 候选路由 | 18.039 ms | 9.419 ms | 41.073 ms |
| 推荐设施完整路线 | 14.212 ms | 12.809 ms | 15.978 ms |
| 响应 Isochrone | 92.581 ms | 63.092 ms | 114.546 ms |
| Emergency API 总时间 | 135.451 ms | 108.732 ms | 156.787 ms |

可重复脚本为 `scripts/validation/phase7_benchmark.py`。

## 11. EXPLAIN (ANALYZE, BUFFERS)

- 中心事件吸附命中 `idx_road_nodes_geography` Index Scan，Execution Time 0.126 ms。
- 医院候选读取分别命中 `ix_pois_subcategory` 与 `ix_pois_category` Bitmap Index Scan，并通过 `poi_routing_access` 关联，Execution Time 0.085 ms。
- 58 个医院映射形成 57 个唯一 source node；many sources → one incident 的 `pgr_dijkstraCost` Function Scan 返回 57 行，Execution Time 14.829 ms。

完整执行计划保存在 benchmark JSON，没有为美化计划修改算法或数据库结构。

## 12. 自动化与浏览器验收

- 完整 pytest：112 passed，包含 Phase 0–6 的 89 项基线与 Phase 7 的 23 项新测试。新测试覆盖真实 medical/fire、参数、吸附、many-to-one SQL、方向、排序、不可达、完整路线、Phase 5 方向回归、Isochrone 嵌套、单向边与 422/404/503。
- `npm run build`：TypeScript 与 Vite 构建通过；保留主 chunk 大于 500 kB 的非阻断提示。
- PostgreSQL 16.4、PostGIS 3.4.3、pgRouting 3.8.0 容器保持 healthy；库内有 8,286 个道路节点、18,441 条有向边、2,308 个 POI 与 106 条设施映射。
- 浏览器确认 API Online、PostGIS Connected；医疗和消防均显示推荐设施、Top 3、事件/吸附点、方向箭头路线与三层响应范围，面板数字与 API 一致。
- 在 `(103.89541,36.03819)` 的医疗事件显示兰州军区空军机关医院、0.57 min、0.28 km、3 edges，并显示 416/2,095/3,442 个 5/10/15 分钟可达节点。
- 在 `(103.77559,36.07096)` 切换消防事件后显示七里河消防队、1.10 min、0.64 km、3 edges，并保留网络最优提示和设施响应范围。
- 快速连续点击只保留最后位置结果；切换 medical/fire 会取消旧请求并更新结果；重新选择、清除和离开模块会移除事件、设施、路线、吸附线与 Isochrone。
- Phase 5 点到点得到 3.19 km、4.80 min、24 edges；最近医院和最近消防站均正常。Phase 6 普通 Isochrone、Phase 3 空间查询（104 POI、792 建筑）、2,307 POI、道路与建筑视窗加载均正常。
- Browser Console 未出现 error 或 warning。

## 13. 已知限制

- 路网成本来自 OSM speed 与 highway 默认速度，不含实时交通、信号灯、事故、天气、道路管制或出警准备时间。
- 没有车辆位置、车辆可用性、人员、调度、事件持久化或多车优化。
- OSM 设施数量、名称和类型可能不完整；一个消防设施没有名称，研究区当前只有 4 个已映射消防站。
- 输入点与设施使用 vertex snapping，接入距离不计入道路时间。
- Isochrone 是可达道路顶点凹壳近似边界，没有对连续道路截止位置插值。
- Vite 主 chunk 仍超过 500 kB，本阶段没有进行大规模前端拆分。

