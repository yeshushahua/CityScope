# Database

`database/Dockerfile` 从锁定 digest 的 `postgis/postgis:16-3.4` 构建，并从 PostgreSQL 官方 APT 仓库安装固定版本 `postgresql-16-pgrouting`。`init/01-enable-postgis.sql` 在全新 volume 中自动启用 PostGIS 与 pgRouting；已有 volume 只需执行迁移或 ETL，不能删除 volume。

迁移按阶段存放在 `migrations/`。Phase 4 的 `004_phase4_routing.sql` 声明 `routing_edges`、外键、正值检查及 GiST/B-tree 索引。Phase 5 的 `005_phase5_routing.sql` 声明道路节点 geography GiST 索引和 `poi_routing_access`；实际映射由 `scripts/osm/build_poi_routing_access.py` 或完整 ETL 幂等构建。

Phase 8 的 `006_phase8_pedestrian_network.sql` 声明独立的 `pedestrian_nodes`、`pedestrian_edges` 和 `poi_walk_access`，包括拓扑外键、正成本约束、geometry/geography GiST 与 source/target/映射索引。真实 OSMnx walk 图和 POI 步行映射由对应脚本以 `--replace` 幂等导入。
