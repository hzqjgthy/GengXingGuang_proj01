# 糖医智辨 Web Demo

一个基于 Flask 和原生前端实现的糖尿病中医智能辅助诊疗教学演示。项目内置三组模拟病例，可在无网络、无模型密钥的情况下完整演示：

`信息采集 -> AI辨证 -> 方剂确认 -> 病历与患者报告`

## 功能

- 三组不同证型的模拟糖尿病病例
- 基本信息、病史、症状、舌象、脉象及检验指标录入
- 千问视觉模型联合分析舌象图片与结构化四诊数据
- 在线模型无密钥、超时、限流、断网或响应无效时直接报错
- 预置演示数据仅在用户主动选择“演示数据”模式时使用
- 候选证型、置信度、判断依据、病机和治法展示
- 方剂及剂量编辑、人工确认和恢复AI建议
- 中医病历、患者版报告及浏览器PDF导出
- 血糖趋势、一键重置和响应式页面

所有病例均为模拟数据。系统只用于教学和项目展示，不构成真实诊断、处方或用药建议。

## 本地运行

```bash
cd /Users/thy/Desktop/KeTiZu/GengXingGuang/code
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

浏览器访问 [http://127.0.0.1:5000](http://127.0.0.1:5000)。

依赖已安装时也可以直接运行：

```bash
make run
```

## 在线模型配置

界面默认选择“在线模型”。未配置密钥时会明确报错，不会自动切换预置结果。配置在线模型时，从示例创建本地配置：

```bash
cp .env.example .env
```

千问多模态示例：

```dotenv
LLM_PROVIDER=qwen
LLM_API_KEY=替换为新生成的密钥
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-vl-max
LLM_TIMEOUT_SECONDS=60
```

不要把真实密钥写入源码、README或提交到版本库。`.env` 已加入 `.gitignore`。此前在对话中暴露过的密钥应先作废，再使用重新生成的密钥。

## 测试

```bash
make test
```

测试不会调用真实在线模型，覆盖病例加载、三类演示辨证、输入校验、动态病例变化、在线模型缺少配置、模型超时报错、人工确认及报告一致性。

## 项目结构

```text
code/
├── app.py                    # Flask入口和API
├── data/                     # 模拟病例和预置分析结果
├── services/                 # AI适配、病例存储、报告生成
├── static/                   # 样式、交互脚本和舌象素材
├── templates/                # Web页面
└── tests/                    # 自动化测试
```
