# CityScope Backend

FastAPI 服务通过 SQLAlchemy、GeoAlchemy2 和 Psycopg 连接 PostGIS。数据库配置统一读取项目根目录 `.env`，请求级 Session 由 `app/db/session.py` 提供。

当前接口：

- `GET /`
- `GET /api/v1/health`
- `GET /api/v1/health/database`
- `GET /api/v1/layers/pois`
- `GET /api/v1/layers/buildings`（必须提供 bbox）
- `GET /api/v1/spatial/nearby-pois`
- `GET /api/v1/spatial/summary`
- `GET /api/v1/network/edges`（必须提供小范围 bbox，可按 highway 过滤）
- `GET /api/v1/network/stats`
- `POST /api/v1/routing/shortest-path`
- `GET /api/v1/routing/nearest-facility`
- `GET /api/v1/routing/isochrone`
- `POST /api/v1/emergency/response`
- `POST /api/v1/living-circle/analyze`

Phase 5 直接使用 `routing_edges` 的静态时间 cost，以 `directed => true` 调用 `pgr_dijkstra` / `pgr_dijkstraCost`。地图点通过 PostGIS 吸附至 500 m 内的道路节点；最近设施按网络时间选择并过滤不可达候选。

Phase 6 对同一静态有向成本执行一次最大 900 秒的 `pgr_drivingDistance`，分离 300/600/900 秒可达顶点，并在 EPSG:32648 中生成合法且嵌套的服务区近似边界。结果固定为 5/10/15 分钟，不包含实时交通或 POI 覆盖统计。

Phase 8 使用独立 `pedestrian_edges` 执行一次最大 900 秒的有向 `pgr_drivingDistance`。4.8 km/h 静态步行速度同时用于路网和居住点/POI connector；POI 生活圈资格按总网络时间判断，凹壳只负责地图表达。

启动、ETL 与测试方法见项目根目录 README。
