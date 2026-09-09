# CityScope

城市空间智能分析与应急响应平台

**Current Status: Phase 8 - Completed**

CityScope 是以兰州市连续主城区及周边建成区为示范区域的 WebGIS 作品。当前已建立真实数据与基础空间查询链：

```text
OpenStreetMap → OSMnx 有向机动车/步行路网 ETL → PostGIS + pgRouting → FastAPI → MapLibre
```

地图业务图层来自本地 PostGIS，不使用手写坐标或静态假数据。当前 Demo bbox 为 `(103.60, 35.98, 104.08, 36.16)`、CRS 为 EPSG:4326；它代表兰州市主城区示范研究区，不代表完整兰州市行政辖区。

Phase 1–7 的地图、真实 PostGIS 数据、空间查询、有向机动车路径、最近设施、机动车 Isochrone 和应急响应决策支持保持可用。Phase 8 增加 15-minute walking living-circle analysis：独立 OSM pedestrian network、network-time-based POI accessibility 和 service-category presence coverage。系统用 4.8 km/h static walking-speed assumption 计算居住点 connector、步行网络成本和 POI connector；结果表达网络可达性与设施类别存在情况，不作官方规划达标判断。

## 技术栈

- 前端：React、TypeScript、Vite、Axios、MapLibre GL JS
- 后端：FastAPI、SQLAlchemy、GeoAlchemy2、Psycopg
- 空间数据：PostgreSQL 16、PostGIS 3.4、pgRouting 3.8、OSMnx、GeoPandas、Shapely、PyProj
- 测试：pytest、FastAPI TestClient、真实 PostGIS 集成测试、浏览器验收

## 目录

```text
CityScope/
├── frontend/src/
│   ├── components/map/layers/  # POI、建筑、路网与路径结果图层
│   ├── components/routing/     # 点到点与最近设施面板
│   ├── components/emergency/   # 医疗与消防应急响应面板
│   ├── components/livingCircle/# 步行15分钟生活圈面板
│   ├── components/layout/
│   ├── services/               # 统一 API 请求
│   └── types/
├── backend/app/
│   ├── api/                    # 健康、空间、路由、应急与生活圈 API
│   ├── db/                     # engine、session、declarative base
│   ├── models/                 # PostGIS 表模型
│   ├── schemas/
│   └── services/               # PostGIS / pgRouting 业务查询
├── backend/tests/
├── database/                   # PostGIS + pgRouting 镜像、init 与迁移
├── scripts/osm/                # 机动车/步行网络、POI映射与数据 ETL
├── data/sample/                # 可提交的小型真实样本
├── docs/
└── docker-compose.yml
```

## 环境准备

在项目根目录复制配置并安装依赖：

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe -m pip install -r scripts/osm/requirements.txt
cd frontend
npm ci
cd ..
```

`.env` 仅用于本地开发且已忽略；部署前必须替换示例密码。

## 启动 PostGIS 与准备数据

```powershell
docker compose up --build -d postgres
.\.venv\Scripts\python.exe scripts/osm/prepare_lanzhou.py --replace
.\.venv\Scripts\python.exe scripts/osm/build_pedestrian_network.py --replace
```

Compose 从锁定的 PostGIS 16-3.4 基础镜像构建并安装固定版本 pgRouting。ETL 将机动车与步行 GraphML、建筑和 POI GeoPackage 缓存到 `data/raw/osm/`，清洗结果放在 `data/interim/osm/`，这些大文件均不提交 Git。`prepare_lanzhou.py --replace` 重建基础业务与机动车网络；`build_pedestrian_network.py --replace` 幂等重建独立的 OSMnx walk 网络和 POI 步行节点映射。

## 本地运行

后端：

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端（另开终端）：

```powershell
cd frontend
npm run dev
```

访问 `http://localhost:5173`。POI 默认加载；道路网络与建筑默认关闭，开启后分别在 zoom 13 和 14 以上按当前地图 bbox 加载。

## API

- `GET /`：服务信息
- `GET /api/v1/health`：API 健康状态
- `GET /api/v1/health/database`：PostgreSQL/PostGIS 真实连接状态
- `GET /api/v1/layers/pois?bbox=...&category=healthcare&subcategory=hospital&limit=...`
- `GET /api/v1/layers/buildings?bbox=west,south,east,north&limit=...`
- `GET /api/v1/spatial/nearby-pois?lon=...&lat=...&radius_m=...&category=...&subcategory=...&limit=...`
- `GET /api/v1/spatial/summary?lon=...&lat=...&radius_m=...`
- `GET /api/v1/network/edges?bbox=west,south,east,north&highway=primary&limit=...`
- `GET /api/v1/network/stats`
- `POST /api/v1/routing/shortest-path`
- `GET /api/v1/routing/nearest-facility?lon=...&lat=...&category=healthcare&subcategory=hospital&limit=5`
- `GET /api/v1/routing/isochrone?lon=103.8343&lat=36.0611&max_snap_m=500`
- `POST /api/v1/emergency/response`：医疗/消防设施 many sources → one incident 响应分析
- `POST /api/v1/living-circle/analyze`：5/10/15 分钟步行圈与 15 分钟网络可达生活服务

建筑接口强制要求小范围 bbox；空间过滤使用 PostGIS `ST_Intersects` 与 `ST_MakeEnvelope`。

## 验证

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
npm run preview -- --host 127.0.0.1 --port 4173 --strictPort
```

完整数据准备记录见 [Phase 2 验证文档](docs/phase-2-validation.md)，空间查询见 [Phase 3 验证文档](docs/phase-3-validation.md)，路网结构见 [Phase 4 验证文档](docs/phase-4-validation.md)，Dijkstra 与最近设施见 [Phase 5 验证文档](docs/phase-5-validation.md)，道路时间 Isochrone 见 [Phase 6 验证文档](docs/phase-6-validation.md)，应急响应见 [Phase 7 验证文档](docs/phase-7-validation.md)，步行网络、POI 可达性、真实案例、性能与浏览器验收见 [Phase 8 验证文档](docs/phase-8-validation.md)。

## 数据来源与限制

业务空间数据来自 © OpenStreetMap contributors。底图 Attribution 保留 OpenFreeMap、OpenMapTiles 与 OpenStreetMap 链接。数据完整性受 OpenStreetMap 社区数据覆盖程度影响。

静态速度是用于网络分析的估计值，不是实时交通速度或实时 ETA。机动车路径和 Isochrone 使用顶点吸附；生活圈则明确把居住点和 POI 的 connector 时间计入总步行时间。所有 Isochrone 边界均为可达节点凹壳近似；生活圈 POI 资格只按网络总时间判断，不按 Polygon 包含关系判断。研究区小连通分量和不可达设施会如实保留并报告。应急模块不含实时交通、车辆位置、出警准备时间或真实调度能力。

## 下一阶段

Phase 9：3D / 专题可视化 / UI 优化（尚未开发）。
