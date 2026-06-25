# Group04-1 智能康复与健身辅助系统

## 1. 项目简介

本目录包含 Group04-1 课程项目的核心代码，当前由三部分组成：

1. `train_stgat_uiprmd.py`
   基于 UI-PRMD 数据集训练多流时空图卷积模型（Multi-Stream ST-GCN），用于康复动作质量二分类。
2. `infer_rehab_folder.py`
   面向视频目录的批量推理脚本，结合 YOLO 姿态估计与离线动作质量判断。
3. `web-flask` + `web-vue`
   前后端分离的智能康复 / 健身辅助系统，支持图片分析、视频分析、实时摄像头、健身计划、体重记录、食物分析和历史记录。

项目目标不是只识别“做了什么动作”，而是进一步判断动作是否规范、是否到位，并给出可解释的分析结果。

## 2. 当前功能概览

### 2.1 离线训练与推理

- 基于 UI-PRMD 的动作质量二分类训练
- 三流输入：`Joint / Bone / Motion`
- 支持生成训练曲线、混淆矩阵、分类报告
- 支持对本地视频目录做批量姿态提取与动作分析

### 2.2 Web 系统

- 用户注册 / 登录 / 个人信息
- 图片动作分析
- 视频动作分析
- 实时摄像头动作检测
- 健身计划与饮食计划管理
- 体重记录
- 食物图片营养分析
- 历史分析记录查看

### 2.3 当前支持的健身动作

后端 `web-flask/services/pose_service.py` 中已实现 7 类动作：

- `squat`：深蹲
- `pushup`：俯卧撑
- `pullup`：引体向上
- `situp`：仰卧起坐
- `bicep_curl`：哑铃弯举
- `shoulder_press`：肩部推举
- `dumbbell_fly`：哑铃飞鸟

## 3. 目录结构

```text
code/
├─ README.md
├─ train_stgat_uiprmd.py
├─ infer_rehab_folder.py
├─ web-flask/
│  ├─ app.py
│  ├─ auth.py
│  ├─ config.py
│  ├─ models.py
│  ├─ requirements.txt
│  ├─ routes/
│  │  ├─ user.py
│  │  ├─ fitness.py
│  │  └─ health.py
│  └─ services/
│     ├─ pose_service.py
│     ├─ video_service.py
│     ├─ ai_service.py
│     └─ camera_state.py
└─ web-vue/
   ├─ package.json
   ├─ vite.config.ts
   └─ src/
      ├─ router/
      ├─ api/
      ├─ stores/
      └─ views/
```

## 4. 技术栈

### 后端

- Flask 3
- Flask-SQLAlchemy
- JWT
- Ultralytics YOLO Pose
- OpenCV
- PyTorch

### 前端

- Vue 3
- TypeScript
- Vite
- Element Plus
- Pinia
- Axios
- ECharts

### 多模态分析

- 阿里云百炼 `Qwen-VL-Plus`

如果未配置百炼 API Key，系统会自动返回模拟分析结果，不会阻塞主流程。

## 5. 运行环境

建议环境：

- Python 3.10+
- Node.js 18+
- npm 9+
- CUDA 环境可选，推荐使用 NVIDIA GPU

## 6. 快速启动

### 6.1 后端启动

进入后端目录：

```bash
cd web-flask
```

安装依赖：

```bash
pip install -r requirements.txt
```

如需使用 Qwen-VL-Plus，请先配置环境变量：

```powershell
$env:DASHSCOPE_API_KEY="你的APIKey"
```

如果使用 `cmd`，可写成：

```cmd
set DASHSCOPE_API_KEY=你的APIKey
```

启动后端：

```bash
python app.py
```

默认运行地址：

- 后端 API: `http://localhost:5000`
- 健康检查: `http://localhost:5000/api/health`

首次启动会自动创建 SQLite 数据库，并自动创建默认管理员账号：

- 用户名：`admin`
- 密码：`admin123`

### 6.2 前端启动

进入前端目录：

```bash
cd web-vue
```

安装依赖：

```bash
npm install
```

启动开发服务器：

```bash
npm run dev
```

默认前端地址：

- `http://localhost:3000`

说明：

- `vite.config.ts` 已配置 `/api -> http://localhost:5000` 代理
- 前后端本地联调时，先启动 Flask，再启动 Vue

## 7. 模型与外部文件说明

### 7.1 YOLO 姿态模型

当前后端默认会尝试在以下路径查找 `yolo11n-pose.pt`：

1. `web-flask/config.py` 中定义的路径
2. `../../rehab_coach/yolo11n-pose.pt`
3. `web-flask/yolo11n-pose.pt`

在当前机器上，代码实际引用的是：

```text
C:\Users\tangvx\Desktop\课程设计\计算机视觉\rehab_coach\yolo11n-pose.pt
```

如果该文件不存在，图片/视频/摄像头分析功能将无法正常运行。

### 7.2 UI-PRMD 数据集

训练脚本默认查找 `data/UI-PRMD`，但当前仓库目录下**未包含数据集本体**。  
运行训练前需要自行补充 UI-PRMD 数据集。

### 7.3 推理脚本的附加依赖

`infer_rehab_folder.py` 当前在文件顶部直接导入：

```python
from ul_red_parser_0 import EXERCISE_ANGLE_MAP, generate_all_templates, load_templates
```

但本目录下**没有** `ul_red_parser_0.py`，因此该脚本目前不是开箱即用状态。  
如果要运行批量推理，需要额外补齐：

- `ul_red_parser_0.py`
- UL-RED 模板 JSON
- 训练得到的 ST-GCN checkpoint

否则脚本会在导入阶段直接报错。

## 8. Web 系统页面说明

前端当前包含 1 个登录页和 8 个核心业务页面：

- `/dashboard`：首页仪表盘
- `/fitness/image`：图片分析
- `/fitness/video`：视频分析
- `/fitness/camera`：实时摄像头
- `/health/plans`：健身与饮食计划
- `/health/weight`：体重记录
- `/health/food`：食物分析
- `/records`：历史记录

## 9. 后端接口概览

### 用户相关

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/profile`
- `PUT /api/auth/profile`

### 健身动作分析

- `GET /api/exercises`
- `POST /api/fitness/image`
- `POST /api/fitness/video`
- `POST /api/camera/start`
- `POST /api/camera/frame`
- `POST /api/camera/snapshot`
- `POST /api/camera/stop`
- `GET /api/records/images`
- `GET /api/records/videos`
- `GET /api/records/videos/<id>/details`
- `GET /api/records/camera`

### 健康管理

- `GET/POST/PUT/DELETE /api/plans/fitness`
- `GET/POST/PUT/DELETE /api/plans/diet`
- `GET/POST /api/plans/exercise`
- `GET/POST /api/weight`
- `POST /api/food/analyze`
- `GET /api/food/records`

## 10. 训练脚本使用方式

训练脚本：

```bash
python train_stgat_uiprmd.py \
  --data-root ./data/UI-PRMD \
  --modality Kinect \
  --feature-type Positions \
  --sequence-length 96 \
  --batch-size 128 \
  --epochs 2000 \
  --lr 1e-3 \
  --dropout 0.35 \
  --projection-dim 128 \
  --temperature 0.10 \
  --early-stop-patience 200 \
  --threshold-mode per-action
```

关键参数：

- `--sequence-length 96`
- `--batch-size 128`
- `--epochs 2000`
- `--lr 1e-3`
- `--dropout 0.35`
- `--projection-dim 128`
- `--temperature 0.10`

## 11. 批量推理脚本使用方式

仅在补齐附加依赖后再运行：

```bash
python infer_rehab_folder.py \
  --video-dir ./test_videos \
  --output-root ./results \
  --method both \
  --yolo-model yolo11n-pose.pt \
  --stgcn-checkpoint ./results/uiprmd_stgcn_kinect_multistream_loso_20260615_090311 \
  --stgcn-threshold 0.5 \
  --dtw-template-json ./data/templates/ul_red_templates.json
```

说明：

- `--method` 可选：`dtw` / `stgcn` / `both`
- 当前脚本依赖额外的 UL-RED 解析模块，不补文件无法直接运行

## 12. 实验结果（现有记录）

根据当前项目已有记录，离线训练结果为：

- 最佳 epoch：`672`
- Accuracy：`0.9800`
- F1-score：`0.9799`

这组指标对应的是 **UI-PRMD 离线动作质量评估模型**，不等同于 Web 实时系统的端到端精度。

## 13. 已知注意事项

1. 当前仓库不包含 UI-PRMD 数据集本体。
2. 当前仓库不包含 `ul_red_parser_0.py`，批量推理脚本不是开箱即用状态。
3. Qwen-VL-Plus 未配置 API Key 时，会回退到模拟分析结果。
4. 姿态分析功能依赖 `yolo11n-pose.pt` 模型文件，需提前放到可搜索路径。
5. 后端默认数据库为 SQLite，路径为 `web-flask/database/fitness.db`。

## 14. 建议的使用顺序

如果你只是想快速演示系统，建议按这个顺序：

1. 准备好 `yolo11n-pose.pt`
2. 启动 `web-flask`
3. 启动 `web-vue`
4. 使用 `admin / admin123` 登录
5. 先测试图片分析，再测试视频分析和实时摄像头

如果你要复现实验训练，再额外准备：

1. UI-PRMD 数据集
2. PyTorch / CUDA 环境
3. 足够的训练时间与显存
