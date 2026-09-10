# 兰州市城市应急响应分析

[English Version](scenario-emergency-response-en.md) | 中文

**Urban Emergency Response Analysis in Lanzhou**

本案例使用 CityScope 当前数据库与 API 的真实结果，展示任意事件点如何经过 Edge Snapping、候选医疗设施网络时间排序、`facility → incident` 路由、5 / 10 / 15 分钟响应范围与高德当前导航对照。结果采集于 **2026-09-10 16:21（Asia/Shanghai）**；高德结果具有时效性，重新运行时可能变化。

## 1. Scenario Background

假设兰州市研究区内发生一宗医疗事件。空间上最近的医院不一定能沿真实道路方向最快抵达，因此设施选择必须基于有向机动车路网的通行时间，而不是只比较直线距离。

## 2. Analysis Objective

本案例回答三个问题：

1. 哪个医疗设施能沿道路网络最快到达事件点？
2. 推荐设施到事件点的实际网络路线、距离与静态 ETA 是什么？
3. CityScope 静态路网基准与高德当前导航估计有何差异？

## 3. Data and Network

分析使用当前兰州示范数据集中的真实 OpenStreetMap 道路、建筑和 POI。机动车网络保存在 PostGIS 中，并由 pgRouting 以 `directed = true` 计算；18,439 条路由边均保持 `reverse_cost = -1`，双向道路由两条真实 directed edge 表示。

静态时间成本使用按 `highway` 类型校准的有效速度。可解析的 OSM `maxspeed` 只作为速度上限。该模型提供稳定的静态基准，不包含实时拥堵、信号灯固定延误、转向惩罚或动态速度。

## 4. Incident Location

浏览器地图中选择的事件点为：

| Item | Value |
| --- | ---: |
| Incident longitude | 103.783489 |
| Incident latitude | 36.058598 |
| Incident type | medical |
| Candidate limit | 5 |

该位置位于当前研究范围内，周边存在多个已映射医院，并且 shortest-path、nearest-facility、isochrone、emergency response 与 traffic-comparison 均返回 HTTP 200。

## 5. Edge Snapping

事件点不被强制移动到最近路网节点。CityScope 将它投影到最近的可路由 edge，并从 edge 内部的真实位置开始计算：

```text
Raw incident point
        ↓
Nearest routable edge
        ↓
Projected point + fraction
        ↓
pgr_withPoints routing
```

本次事件点的实际吸附结果为：

| Item | Value |
| --- | ---: |
| Edge ID | 8,884 |
| Source | 4,185,030,235 |
| Target | 11,293,237,382 |
| Fraction | 0.133452809576 |
| Snapped longitude | 103.783552783611 |
| Snapped latitude | 36.058617400766 |
| Snap distance | 6.1 m |

推荐设施同样投影到 edge 3,681，fraction 为 0.279652868552，设施吸附距离为 28.0 m。原始点到投影点的 connector 只作为 metadata 返回，没有加入路由距离或 ETA。

## 6. Network-Based Facility Selection

应急接口检查了 58 个已映射医院，其中 57 个可以沿有向路网到达事件点，返回网络时间最短的 5 个候选。排序方向保持为 `facility → incident`。

| Network rank | Facility | Straight distance | Response ETA |
| ---: | --- | ---: | ---: |
| 1 | 七里河区中药医院 | 1,521.4 m | 218.3 s / 3.64 min |
| 2 | 甘肃省肿瘤医院 | 1,029.9 m | 296.0 s / 4.93 min |
| 3 | 甘肃省妇幼保健院 | 1,549.0 m | 299.7 s / 4.99 min |
| 4 | 未命名医院（POI 626） | 2,168.6 m | 317.9 s / 5.30 min |
| 5 | 第九四〇医院 | 1,207.2 m | 321.8 s / 5.36 min |

| Selection criterion | Facility |
| --- | --- |
| Nearest by straight-line distance | 甘肃省肿瘤医院（POI 1052） |
| Fastest by facility-to-incident network time | 七里河区中药医院（POI 1022） |

这组真实结果说明，直线距离最短并不等于在道路方向和时间成本约束下响应最快。独立的 `nearest-facility` 接口从事件点向设施计算 `incident → facility`，本次返回甘肃省肿瘤医院；它与应急调度要求的反向行程并非同一问题。

## 7. Emergency Response Route

推荐设施为 **七里河区中药医院**，原始坐标为 `(103.799750850710, 36.054905750000)`。实际响应路线保持 `facility → incident`：

| Metric | Result |
| --- | ---: |
| Network distance | 2,003.0 m |
| Static response time | 218.3 s / 3.64 min |
| Average speed derived from returned distance and time | 33.03 km/h |
| Traversed directed edges | 13 |

单独调用 shortest-path 使用相同起终点时，返回相同的 2,003.0 m、218.3 s 和 13 条 directed edge，验证了应急路线与通用路径服务的一致性。

## 8. 5 / 10 / 15 Minute Response Coverage

响应范围以推荐设施的 edge-snapped 位置为起点，通过 `pgr_withPointsDD` 计算可达节点，再生成用于地图表达的 Concave Hull。

| Time band | Reachable nodes | Approximate area |
| ---: | ---: | ---: |
| 5 min | 191 | 4.060 km² |
| 10 min | 1,286 | 32.002 km² |
| 15 min | 2,820 | 111.626 km² |

三组可达节点数量与面积随阈值单调增加。边界是对可达网络节点的空间近似，不代表行政边界或实时应急服务承诺。

## 9. CityScope Static ETA vs AMap Current Navigation

对照请求使用完全相同的方向和原始坐标：七里河区中药医院 → 事件点。

| Metric | CityScope Static Baseline | AMap Current Navigation |
| --- | ---: | ---: |
| Distance | 2,003.0 m | 2,027.0 m |
| ETA | 218.3 s / 3.64 min | 563.0 s / 9.38 min |
| Average speed | 33.03 km/h | 12.96 km/h |

高德本次还返回：2 个交通灯、0 元通行费、1 条候选路线；TMC 组成是畅通 1,452 m、拥堵 330 m、未知 245 m，缓行与严重拥堵均为 0 m。

CityScope 表示基于 OSM、pgRouting 和校准后静态有效速度的 **Static Routing Baseline**；高德表示采集时刻的 **Current Navigation Estimate**。两者 ETA 相差 344.7 s，但该差值不能直接解释为纯拥堵延误，因为交通状态、信号灯、路线选择、路口条件、坐标转换与导航模型都会共同影响结果。

## 10. Findings

- 按道路网络时间排序改变了设施选择：直线最近的甘肃省肿瘤医院没有成为 `facility → incident` 最快响应设施。
- 6.1 m 的事件点 Edge Snapping 让路由从道路内部投影点开始，并保留首尾 edge 的部分成本。
- 5 / 10 / 15 分钟响应范围提供了同一静态成本模型下的分级服务覆盖表达。
- CityScope 与高德结果适合用于比较不同交通假设，不构成严格的导航精度评测。

## 11. Reproduction

启动数据库、后端与前端后，可以在页面的“应急响应”模块选择医疗事件，并点击 `(103.783489, 36.058598)` 附近。也可以直接调用 API：

```bash
curl -X POST http://localhost:8000/api/v1/emergency/response \
  -H "Content-Type: application/json" \
  -d '{"incident":{"lon":103.783489,"lat":36.058598},"incident_type":"medical","candidate_limit":5}'
```

```bash
curl -X POST http://localhost:8000/api/v1/routing/traffic-comparison \
  -H "Content-Type: application/json" \
  -d '{"start":{"lon":103.79975085070964,"lat":36.05490575},"end":{"lon":103.783489,"lat":36.058598}}'
```

高德结果依赖有效的 `AMAP_WEB_SERVICE_KEY`、网络状态和请求时间，因此再次执行时应以新的接口返回值为准。

## 12. Technical Notes

- 数据坐标系：EPSG:4326；距离和投影计算使用适合研究区的米制坐标或 PostGIS geography。
- 路由函数：`pgr_withPoints`、`pgr_withPointsCost`、`pgr_withPointsDD`。
- 有向约束：`directed = true`、`reverse_cost = -1`。
- 39 条 `source = target` 的原始 self-loop edge 保留在路网中，但不参与 Edge Snapping 候选。
- 本案例是空间决策演示，不是真实医疗调度建议。
