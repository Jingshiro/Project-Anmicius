# Project Anmicius

Project Anmicius 是一款基于 Python 开发的智能桌面伴侣应用程序。该项目旨在提供一个高度可定制的虚拟助手，集成 AI 对话、健康管理及桌面交互功能。

---

## 目录

- [用户手册](#用户手册)
  - [产品概述](#产品概述)
  - [核心功能](#核心功能)
  - [快速开始](#快速开始)
- [开发者文档](#开发者文档)
  - [技术架构](#技术架构)
  - [环境搭建](#环境搭建)
  - [扩展开发](#扩展开发)
  - [构建发布](#构建发布)
- [版权与许可](#版权与许可)

---

## 用户手册

### 产品概述

Project Anmicius 在桌面运行一个虚拟角色，该角色具备自然语言交互能力，并作为用户的个人健康管家。系统支持多角色切换、自定义人设、视觉反馈及各类定时提醒。

### 核心功能

#### 智能交互系统

- **自然语言对话**：基于 LLM (大语言模型) API，支持上下文连续对话
- **角色扮演**：系统严格遵循设定的人设（Persona）进行回应
- **触摸反馈**：支持自定义角色的头部、肢体等触摸区域，触发特定的动作与语音反馈

#### 健康管理模块

- **水分摄入提醒**：基于设定的时间间隔或固定时刻提醒饮水
- **久坐干预**：监测非活跃时间，定时提醒用户起立活动
- **膳食提醒**：覆盖早餐、午餐、晚餐的固定时间提醒
- **视力保护**：定期提醒放松眼部与大脑
- **生理周期追踪**：可选功能，提供周期记录与预测
- **用药管理**：支持自定义药品名称与服用时间的提醒

#### 个性化定制

- **多角色管理**：支持创建、导入、导出多个独立角色
- **外观定制**：支持自定义角色立绘（Avatar）、表情差分及对话气泡样式
- **场景感知**：根据时间段（工作日/周末）自动调整活跃状态

### 快速开始

#### 启动程序

运行安装目录下的 `ProjectAnmicius.exe` 或 `run.bat`。

[开袋即食版](https://github.com/Jingshiro/Project-Anmicius/releases/download/v1.0/ProjectAnmicius.exe)

#### 初始配置

首次启动后，右键点击桌面角色图标，选择"设置"。

- **API 设置**：输入兼容 OpenAI 格式的 API Key 及 Base URL
- **角色设定**：可修改默认角色的名称、人设描述及用户称呼

#### 操作交互

- **左键点击**：触发随机对话或特定区域反馈
- **右键点击**：打开功能菜单（设置、隐藏、退出等）
- **对话框**：点击气泡输入文字进行对话

---

## 开发者文档

### 技术架构

本项目基于 Python 开发，采用模块化设计。

#### 技术栈

| 组件     | 技术选型      | 用途               |
| -------- | ------------- | ------------------ |
| 核心语言 | Python 3.8+   | 主程序逻辑         |
| GUI 框架 | customtkinter | 现代化图形界面     |
| 图像处理 | Pillow        | 立绘加载与处理     |
| 系统托盘 | pystray       | 后台运行与托盘图标 |
| 拼音转换 | pypinyin      | 角色 ID 自动生成   |
| 打包工具 | PyInstaller   | 生成独立可执行文件 |

#### 目录结构

```text
Project Anmicius/
├── main.py                  # 程序入口与主逻辑
├── config_manager.py        # 配置管理与数据持久化
├── ai_client.py             # AI API 交互模块
├── utils.py                 # 通用工具函数库
├── build.py                 # 构建脚本
├── prompt_templates.json    # AI 提示词模板
├── config.json              # 运行时配置文件
├── requirements.txt         # 项目依赖清单
└── characters/              # 角色资源目录
    └── char_xxxx/           # 单个角色数据
        ├── character.png    # 默认立绘
        └── expressions/     # 表情差分文件
```

### 环境搭建

#### 前置要求

- Python 3.8 或更高版本
- pip 包管理器

#### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/Jingshiro/Project-Anmicius
.git
cd ProjectAnmicius

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行程序
python main.py
```

### 扩展开发

#### 提示词系统 (Prompt Engineering)

所有与 AI 交互的 Prompt 模板均定义在 `prompt_templates.json` 中。

- **模板变量**：支持 `{user}`, `{char}`, `{persona}`, `{cups}`, `{target}` 等动态变量
- **自定义场景**：可添加新的提示词类型，如节日问候、特殊事件等

#### 角色数据结构

角色配置以 JSON 格式存储于 `config.json`，支持导出为独立的 ZIP 包。

- **SillyTavern 兼容**：支持导入 SillyTavern 格式的角色卡（PNG 元数据）
- **Lorebook 系统**：支持关键词触发的背景知识注入

#### API 集成

系统兼容 OpenAI Chat Completion 格式的 API。若使用自建 API，需确保：

- 支持 `/v1/chat/completions` 端点
- 返回格式符合 OpenAI 规范

### 构建发布

#### 构建命令

```bash
python build.py
```

或直接运行：

```bash
build.bat
```

构建产物将输出至 `dist/` 目录。构建过程会自动处理：

- 资源文件打包与路径映射
- 依赖库的嵌入与优化
- 生成单文件可执行程序 (EXE)

---

## 版权与许可

### 开发者信息

- **开发者**：镜 (Jingshiro)
- **GitHub**：[https://github.com/Jingshiro](https://github.com/Jingshiro)
- **联系邮箱**：jingbaichuan1@gmail.com

### 许可协议

本项目采用 **CC BY-NC-SA 4.0 + 附加条款** 许可协议。

#### 基础许可：CC BY-NC-SA 4.0

本项目遵循 [知识共享署名-非商业性使用-相同方式共享 4.0 国际许可协议 (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/)。

核心条款：

- **署名 (Attribution)**：使用本项目时需注明原作者信息
- **非商业性使用 (NonCommercial)**：禁止将本项目用于任何商业目的
- **相同方式共享 (ShareAlike)**：修改后的作品需采用相同许可协议

#### 附加条款

- **二次分发与修改需告知**：任何形式的二次分发（转载、打包）或二次修改（Fork、改编），请通过邮件告知原作者。

### 贡献指南

本项目完全开源免费。欢迎通过以下方式参与：

- 提交 Bug 报告或功能建议：[GitHub Issues](https://github.com/Jingshiro/ProjectAnmicius/issues)
- 贡献代码：提交 Pull Request 前请先通过 Issue 讨论
- 技术交流：通过邮件或 GitHub Discussions 与开发者联系

---

**Project Anmicius** © 2025 镜. All Rights Reserved.
