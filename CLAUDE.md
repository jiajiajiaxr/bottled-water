# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AgentHub (codename `fish`) is a multi-agent collaboration IM workbench. It combines chat sessions, group conversations, an Agent marketplace, model management, tools, Skills, MCP, file context, artifact generation, a workflow canvas, and audit/permissions into a single platform.

项目的文档位于`docs/`目录下，包括项目介绍和更详细的功能设计。

## 开发规范

### 总述

该项目是经典的前后端分离项目，前端使用React 18 + TypeScript + Vite + Ant Design，后端使用Python 3.11 + FastAPI + SQLAlchemy + Alembic。

其中，前端代码位于`frontend/`目录，后端代码位于`backend/`目录。

绝大多数情况下，都可以认为开发行为在Windows环境下进行，因此，优先使用powershell命令或者PowerShell工具进行各种开发指令的执行。

### 后端开发

- 后端的唯一开发语言为Python，同时使用`uv`作为项目管理工具，因此，一切跟后端开发有关的操作，都必须在`backend/`目录下进行，并且使用`uv`相关命令。
- 后端开发采用模块化设计，因此，严格禁止过长的函数和过大的文件。一般来说，单个函数不应该超过100行，单个文件不应该超过500行。
- 后端开发需要编写单元测试，测试代码应该放在`backend/tests/`目录下，并且使用`pytest`框架进行测试。因此，所有后端的功能都必须存在测试，也必须通过测试。
- 代码应该符合PEP8规范，包括缩进、空格、注释等。函数、类、模块等都应该有适当的注释，说明其作用和参数，使用谷歌的注释规范，并且注释内容应当使用中文。
- 代码使用`Ruff`进行代码规范检查和格式化，因此，所有后端代码都必须符合相关规范，并且在提交之前必须通过Ruff的检查。

### 前端开发

- 前端的唯一开发语言为TypeScript（Ts/Tsx），同时使用`pnpm`作为项目管理工具，因此，一切跟前端开发有关的操作，都必须在`frontend/`目录下进行，并且使用`pnpm`相关命令，除了基本命令，项目自行定义的命令，见`frontend/package.json`。
- 前端开发采用组件化设计，因此，严格禁止过长的函数和过大的文件。一般来说，单个函数不应该超过100行，单个文件不应该超过500行。
- 前端开发使用Eslint和Prettier进行代码规范检查和格式化，因此，所有前端代码都必须符合相关规范，并且在提交之前必须通过Eslint的检查。
- 代码应该符合Airbnb的JavaScript/TypeScript规范，包括缩进、空格、注释等。函数、类、模块等都应该有适当的注释，说明其作用和参数，使用JSDoc的注释规范，并且注释内容应当使用中文。

### 代码提交规范

- 所有代码提交必须使用Git，并且遵循Git Flow的分支管理规范。
- 所有的提交遵循Angular的提交规范，即`type(scope): subject`，其中`type`是提交的类型，`scope`是提交的影响范围，`subject`是提交的描述。
- 所有的代码修改（包括新增、修改、删除）都必须提交。
