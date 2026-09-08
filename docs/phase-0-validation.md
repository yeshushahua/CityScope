# Phase 0 验证记录

验证日期：2026-09-07。

- Git 2.45.1.windows.1，已初始化仓库，未创建提交或远程仓库。
- 系统 Python 3.9.9 / pip 24.3.1；本次隔离环境 Python 3.12.14 / pip 25.0.1。
- Node 24.19.0；系统未提供 npm，使用工作目录外层的临时 npm 12.0.2 完成安装、构建与启动，没有系统安装。
- npm install 成功，审计 0 vulnerabilities，package-lock.json 已生成。
- npm run build 成功，Vite 6.4.3，84 modules transformed。
- npm run dev 成功，端口 5173。
- Uvicorn --reload 成功，端口 8000。
- GET / 与 GET /api/v1/health 实际 HTTP 返回符合要求。
- 浏览器显示 CityScope、中文副标题、System Ready、Backend: Online。
- 停止后端并刷新，浏览器显示 Backend: Offline。
- pytest：4 passed，退出码 0；Starlette/AnyIO 有一条 BlockingPortal 弃用提示，不影响测试。
- Git 忽略验证：根目录与前端 .env、虚拟环境、node_modules、dist、raw/interim 数据均被忽略；data/sample 可跟踪。
- 无业务表、OSM 导入、地图或后续分析功能。

限制：未安装 Docker / Docker Compose，未实际运行容器或验证镜像拉取。Python 3.11 尚未本地验证。建议补齐环境后执行 README 中 Docker 验证命令。Phase 0 本地前后端验收通过，Docker 验收待验证；不宣称全部环境验证完成。

首次沙箱运行阻止前端缓存写入，重新授权项目内构建后成功；后端测试也在授权执行后完整退出。
