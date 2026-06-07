# 英语口语 AI 陪练工具

这是一个基于 Python 标准库实现的英语口语练习 Web 原型，面向成人/学生在网页或移动端进行场景化英语对话训练。系统支持实时语音对话、场景对话管理、发音评测、语法纠错、表达升级、延迟拆分和课后总结。

## 启动

```powershell
python app.py
```

如果系统 `python` 命令不可用，可使用 Codex 工作区自带解释器：

```powershell
& "C:\Users\Mark\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" app.py
```

浏览器打开：

```text
http://127.0.0.1:8000
```

建议使用 Chrome 或 Edge，并允许麦克风权限。语音不可用时可以使用文本输入继续练习。

## 当前功能

- P0 实时语音对话：浏览器 Web Speech API 负责 ASR，SpeechSynthesis 负责 TTS，Python 后端负责对话策略和反馈。
- P0 发音评测反馈：提供 GOP-style 评分接口，返回总体发音分、语速、填充词、音素风险项和改进建议。
- P1 语法纠错：检测常见口语语法、时态、搭配和词形错误，并在每轮回答后反馈。
- P1 场景模板和对话管理：内置餐厅点餐、旅行问路、求职面试、商务会议、雅思口语。
- P2 低延迟指标：返回 ASR/NLU/Scoring/DM/LLM/TTS 延迟拆分，便于后续接入流式链路。
- P2 多轮上下文：记录会话历史、意图、槽位和场景完成度。
- 隐私控制：提供删除本地会话与学习进度的接口。

## 生产化替换点

当前项目保持零依赖、可离线运行，因此 ASR/TTS/GOP 是浏览器或规则型 demo adapter。生产环境建议替换如下：

- ASR：将 Web Speech API 替换为流式 Whisper、讯飞、腾讯云或 WebRTC + WebSocket ASR。
- TTS：将浏览器 TTS 替换为流式句子级 TTS，降低首包等待时间。
- LLM：设置 `OPENAI_API_KEY` 后后端会调用 OpenAI Responses API；也可替换为私有 LLaMA/ChatGLM 服务。
- 发音评测：`assess_pronunciation()` 已预留 `audioFeatures` 输入，可接入 Kaldi/GOP、音素对齐、音高、时长、重音等声学特征。
- 语法纠错：可把 `find_corrections()` 替换为 LanguageTool、BART/GEC 模型或 LLM 纠错服务。
- 记忆系统：当前学习进度保存在内存，生产环境应换为数据库并提供加密、删除和导出能力。

## API

- `GET /api/scenarios`：场景目录
- `POST /api/start`：开始会话
- `POST /api/respond`：提交用户话语并获取 AI 回复、评分和反馈
- `POST /api/revise`：修正上一句 ASR 文本
- `POST /api/summary`：生成课后总结
- `POST /api/delete-user-data`：删除本地用户数据

## 可选 AI 增强

```powershell
$env:OPENAI_API_KEY="你的 API Key"
$env:OPENAI_MODEL="gpt-4.1-mini"
python app.py
```

如果 API 不可用，系统会自动回退到本地对话管理器。

demo:https://www.bilibili.com/video/BV11cE46wETp/
