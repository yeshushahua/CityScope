# Phase 9 验证记录

## 状态

**PASS** — 2026-09-09

本阶段在 Phase 8 提交 `cf290c9` 上渐进完成专题可视化、MapLibre 2.5D/3D 建筑和 UI 产品化优化。没有修改路径成本、Isochrone、应急推荐或生活圈算法，也没有进入 Phase 10。

## UI 与设计系统

- 在 `style.css` 中建立背景、文字、边框、业务状态、间距、圆角、阴影、动画和层级的语义变量。
- Header 分别显示真实 Backend 与 PostGIS 状态；Sidebar 按地图展示、基础分析、出行分析和城市业务分组。
- 使用项目内轻量 SVG 图标，统一面板标题、参数、结果、模型说明、加载、错误、空状态、按钮和键盘焦点。
- 建立统一数字格式工具，规范 `m`、`km`、`m²`、`km²`、`s`、`min`、`km/h` 和坐标精度。

## 地图专题表达

- Map Legend 随城市总览、空间查询、点到点、最近设施、机动车 Isochrone、应急响应和生活圈动态变化。
- Layers 可控制基础 POI、建筑、道路网络、当前分析结果和 3D 建筑拉伸。
- 基础 POI 使用 MapLibre GeoJSON clustering；业务分析 POI 继续保持独立、完整、可点击。
- 道路仍在 zoom 13+、建筑仍在 zoom 14+ 按当前 bbox 加载，并保留 AbortController。
- 5/10/15 分钟色阶、路线、应急路线和服务类别颜色由统一语义配置驱动。

## 2.5D/3D 建筑

实现使用 MapLibre GL JS 原生 `fill-extrusion`。默认保持 2D；进入 3D 时使用 `pitch=52`、`bearing=-18`，并提供返回 2D和恢复北向/兰州视图。分析结果层在建筑层之后创建，浏览器中确认路线、事件点、设施和可达圈在 3D 下仍可读。

高度只从本地已有 OSMnx 响应缓存中的真实 OSM tags 恢复：

| 来源 | 数量 | 展示规则 |
| --- | ---: | --- |
| `osm_height` | 1,749 | 使用有效 OSM `height`，3–280 m |
| `levels_estimate` | 57 | 无 height 时使用 `building:levels × 3 m`，6–132 m |
| `unknown` | 28,205 | 保持平面，不生成高度 |
| 总计 | 30,011 | 与数据库建筑总数一致 |

数据库中有 263 栋同时存在有效 `height` 和 `building:levels`，按优先级计入 `osm_height`；有效 levels tag 共 320 栋，真正使用楼层估算的为 57 栋。一个零值 tag 被判定为无效并保持未知。

数据库一致性检查 `bad_osm=0`、`bad_levels=0`、`bad_unknown=0`。抽查文件记录 10 栋 OSM 高度、10 栋楼层估算和 3 栋未知高度，共 23 栋；满足至少 20 栋有高度来源建筑的抽查要求。重复执行回填所得摘要哈希均为 `07d61901130b6b6f2112d9a67557a50610a7f0fba3afea27fe42393fbf25b878`。

浏览器实际点击确认：OSM height 建筑显示原始高度；`研究生公寓3号` 显示 `18.0 m（6 层 × 3 m）`；未知高度建筑显示“未知，保持平面”。完整样本和统计见 `phase-9-frontend-benchmark.json`。

## 真实结果图表

- 空间查询使用 API 分类统计显示 POI 类别水平条形图。
- 生活圈使用真实 15 分钟 `reachable_poi_count` 显示商业、医疗、教育、休闲和交通分布。
- 没有引入 ECharts；当前两处小型分类分布用可访问的 CSS 条形图即可表达，避免增加大型依赖和虚假图表。

## Bundle

Phase 8 基线：108 modules，main `1,281.03 kB` / gzip `354.98 kB`，CSS `104.58 kB` / gzip `14.59 kB`，worker `487.15 kB`。

Phase 9：115 modules，入口 main `85.86 kB` / gzip `29.86 kB`；按需 CityMap `36.57 kB` / gzip `9.64 kB`；React vendor `186.49 kB` / gzip `58.53 kB`；MapLibre vendor `981.07 kB` / gzip `260.51 kB`；应用 CSS `30.52 kB` / gzip `6.19 kB`；MapLibre CSS `83.04 kB` / gzip `10.52 kB`；worker `487.15 kB`。

入口 main 比 Phase 8 减少 `1,195.17 kB`（约 93.3%），gzip 减少 `325.12 kB`（约 91.6%）。Vite 仍提示 MapLibre vendor 超过 500 kB；该 chunk 是独立地图引擎依赖，入口和业务代码边界已经清晰，MapLibre worker、CSS 和浏览器地图加载均正常。

## 浏览器验收

在真实运行的 FastAPI、PostGIS 和 Vite 开发服务上完成：

1. 默认地图、Header 双状态、分组 Sidebar 和当前模块高亮正常。
2. 空间查询显示查询圆、113 个附近 POI、911 栋相交建筑、816,481 m² 建筑占地和真实类别图；连续快速点击后仅保留最后位置结果，无 AbortController 异常。
3. 道路视窗加载 745 条边；Road Popup 显示 highway、长度、静态速度及来源、时间、方向、节点和 OSM ID。
4. 点到点路径先验证无可达路径的产品化 404，再重选获得 351 m、42 s、3 条道路边的有效路线。
5. 最近医院返回甘肃省康复中心医院 595 m / 57 s；最近消防返回七里河消防队 10.32 km / 12.3 min。
6. 机动车 Isochrone 返回 5/10/15 分钟 856/2,507/3,931 个节点和真实面积，动态图例匹配。
7. 医疗应急返回甘肃省康复中心医院 593 m / 57 s；消防应急返回七里河消防队 10.20 km / 12.9 min，候选设施、响应路线和圈层正常。
8. 步行生活圈返回 5/5 类覆盖、68 个 15 分钟核心 POI、真实五分类图；类别筛选、重新选择和清除正常。
9. Layers 开关、2D→3D、3D 建筑、3D 路线、3D Isochrone、恢复 2D 和恢复北向正常。
10. 交互式浏览器精确切换至 1366×768 与 1920×1080 视口，真实底图保持加载；Sidebar、滚动分析面板、地图工具和图例没有互相遮挡。默认 1265×720 视口也完整完成全部地图验收。
11. 浏览器 Console 无关键 error；MapLibre source/layer 未重复注册。远程 OpenFreeMap 字体不再因项目箭头字符产生额外 glyph 404。

## 自动化验证

- `npm run build`：PASS，TypeScript 检查通过，115 modules transformed。
- `pytest -q`：140 passed；其中新增 2 个 Phase 9 建筑展示字段与真实数据库一致性测试。
- PostgreSQL 16.4 / PostGIS 3.4.3 / pgRouting 3.8.0：容器 healthy，数据库健康 API 为 Online。
- 数据库保存 2,308 POI、30,011 buildings、18,441 motor edges 和既有步行网络；本阶段未删除 volume 或重建核心数据。

## 已知限制

- 只有 1,806 / 30,011 栋建筑具备可用展示高度；其余 28,205 栋保持平面，这是 OSM 标签完整度的真实反映。
- 楼层估算按 3 m/层，仅用于可视化，不是实测高度。
- MapLibre vendor chunk 和 worker 仍较大，但已与主入口分离。
- 底图依赖 OpenFreeMap 网络资源；离线时业务 UI 会明确显示地图加载失败。
