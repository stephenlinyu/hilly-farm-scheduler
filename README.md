# 丘陵山地智能农机调度系统（Hilly Farm Scheduler）

面向重庆丘陵山区的智能农机管理系统，解决 **50 台农机、150 块农田** 的任务分配、轨迹追踪、实时定位与路径规划问题。系统由 Flask 后端、遗传算法调度模块和 Leaflet Web 前端组成，支持 SQLite / MySQL 双数据库切换和真实农机（JT/T 808）接入。

> 本项目为脱敏演示版本：不含真实 API 密钥、业务数据库、设备 IMEI 与人员账号。

## 功能

- **调度计算**：Python 版遗传算法（由 MATLAB 迁移而来），通过 Flask 提供 RESTful 调度接口，支持多机并发与候选方案派发
- **双数据库适配**：SQLite（默认）/ MySQL 可切换，8 张核心表
- **JT/T 808 接入**：北斗终端注册、鉴权、心跳、定位上报，WGS84 → GCJ-02 坐标转换
- **Web 可视化**：Leaflet 地图，农机实时定位、农田标记、轨迹回放、标记聚合
- **路径规划**：调度只输出任务顺序，行驶路线基于高德地图 API 按农机当前位置规划
- **接口测试**：pytest + Flask test_client，覆盖登录、调度、轨迹查询等核心接口

## 技术栈

`Python` · `Flask` · `SQLite / MySQL` · `pytest` · `JT/T 808` · `Leaflet` · `高德地图 JS API` · `Waitress`

## 目录结构

```
hilly-farm-scheduler/
├── app.py                  # Flask 应用（API + 页面路由 + 调度编排）
├── run_server.py           # Waitress 启动入口
├── init_local_db.py        # 建表与演示数据初始化
├── ga_solver/              # Python 遗传算法（MATLAB 迁移版）
│   ├── solver.py           # 求解入口
│   ├── ga_main.py          # GA 主循环
│   ├── cost_function.py    # 适应度（距离/海拔/能耗/工时）
│   ├── init_assignment.py  # 初始分配
│   ├── crossover*.py       # 交叉算子
│   ├── mutate.py           # 变异算子
│   └── selection.py        # 选择算子
├── scheduler/              # MATLAB 原版算法与样例数据
├── jt808_codec.py          # JT/T 808 报文编解码
├── jt808_server.py         # 808 TCP 接收服务
├── gpswv_location.py       # 商家云平台定位接入
├── coordinate_converter.py # WGS84 / GCJ-02 坐标转换
├── static/                 # 前端（Leaflet / ECharts）
├── config/*.example.json   # 配置模板（复制后填写自己的密钥）
└── requirements.txt
```

## 快速开始

```bash
pip install -r requirements.txt
python run_server.py
```

浏览器打开 `http://127.0.0.1:5000/login`（管理端）或 `/worker/login`（作业端）。

首次启动会生成 `farm_management.sqlite` 与 `.farm_secret_key`，请在管理端修改默认密码。

### 配置

复制模板并填写自己的 key：

```bash
cp amap_config.example.json amap_config.json        # 高德地图 Web Key
cp gpswv_config.example.json gpswv_config.json      # 可选：商家云平台定位
```

`*.example.json` 中的 IMEI 为占位值，请替换为你的设备号。

## 算法说明

调度目标为最小化总转移距离 / 能耗 / 最大完工时间，约束包括坡度能耗、地块面积与农机工时。算法由 MATLAB 版本迁移到 Python，迁移后通过固定随机种子与数值容差做等价性回归。

## 说明

- 调度算法基于开源项目 **GA_MRTA**（Copyright (c) 2024 Thi Thuy Ngan Duong, MIT License）改进，原许可证见 `scheduler/LICENSE`。
- 本仓库为个人作品展示，数据与配置均已脱敏。
