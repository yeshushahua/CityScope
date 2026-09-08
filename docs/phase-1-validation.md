# Phase 1 验证记录

验证日期：2026-09-07。

## 环境与依赖

- MapLibre GL JS：6.7.0（package-lock.json 精确版本）。
- Node.js：24.19.0。
- npm：系统无全局命令；使用 `node ../../package/bin/npm-cli.js` 调用临时 npm CLI 12.0.2。
- Python：现有隔离环境 3.12.14。
- 底图：`https://tiles.openfreemap.org/styles/liberty`，可通过 `VITE_MAP_STYLE_URL` 覆盖。
- 默认城市：兰州市主城区，中心 103.8343 / 36.0611，zoom 11，pitch 0，bearing 0。

## 实现检查

- 使用 `maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url` 并调用 `setWorkerUrl`。
- 生产构建生成独立的 `maplibre-gl-worker-CJfwIrte.js`，大小 487.15 kB。
- MapLibre 实例保存在 ref 中；卸载时解除自定义事件、断开 ResizeObserver、清理 Popup 并调用 `map.remove()`。
- NavigationControl 位于右上角；ScaleControl 使用 metric；Attribution 保留。
- 鼠标移动显示 WGS84 六位小数；点击地图显示相同坐标格式的 Popup。
- 页面使用固定 Header、非覆盖式 Sidebar 和填满剩余区域的地图容器。
- API 健康检查保留，并为开发端口 5173 和预览端口 4173 配置 CORS。
- 未添加 Marker、业务设施、OSM 下载、PostGIS 连接或空间分析。

## 命令结果

- `npm install maplibre-gl@6.7.0`：成功，审计 0 vulnerabilities，真实更新 package.json 与 package-lock.json。
- `npm run build`：成功；TypeScript 与 Vite 无错误，95 modules transformed。
- `npm run preview -- --host 127.0.0.1 --port 4173 --strictPort`：成功，生产地图与 Worker、瓦片均正常。
- `pytest`：7 passed，退出码 0；有一条 Starlette/AnyIO BlockingPortal 弃用提示。
- `GET /api/v1/health`：200，返回 `{"status":"ok","service":"CityScope API"}`。

## 浏览器测试

开发版和生产预览均实际访问：

- 兰州底图、中英文标注、道路与水系正常加载。
- Zoom in 使比例尺从 3 km 变化为 2 km；拖动后地图与实时坐标均变化。
- 返回兰州恢复中心、zoom 11、pitch 0、bearing 0。
- 地图点击弹出坐标 Popup；中心点验证为 103.834300 / 36.061100。
- Sidebar、Header、API Online、Loading 消失后的地图、NavigationControl、ScaleControl 与 Attribution 正常。
- 未开发模块可切换选中状态并显示“功能将在后续阶段开放”。
- 生产预览 API 初次因 4173 未在 CORS 白名单显示 Offline；修复配置并增加测试后为 Online。
- 模拟底图样式请求失败后，“地图加载失败”正常显示，Header 与 Sidebar 仍保持可见，无整页白屏。

精确视口检查：

| 视口 | 地图区域 | Canvas | 页面溢出 | Console errors | Page errors |
| --- | --- | --- | --- | --- | --- |
| 1366×768 | 1120×700 | 1120×700 | 无 | 0 | 0 |
| 1920×1080 | 1648×1012 | 1648×1012 | 无 | 0 | 0 |

## 已知问题

- Vite 报告主 JavaScript chunk 超过 500 kB；Phase 1 功能与性能验收不受影响。后续模块增多时再按路由或功能进行代码分割。
- pytest 显示一条第三方 Starlette/AnyIO 弃用提示，不影响测试结果。
- 底图依赖公开 OpenFreeMap 网络服务；离线或服务不可用时会进入“地图加载失败”状态。
- 本阶段按指令不处理 Docker。

## 结论

Phase 1 - Completed / PASS。
