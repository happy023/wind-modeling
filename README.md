# Windchill 远程建模工具集

这是一套用于 Windchill 远程建模的工具集，支持通过 SSH/SFTP 远程执行 Windchill 建模相关的操作。工具集包含以下功能：

- 远程目录准备
- 模型文件上传
- 代码和SQL生成
- 生成文件收集
- **Web在线建模服务**（新增）

## 功能特点

- 基于 SSH/SFTP 的远程操作
- 支持批量处理多个模型类
- 完整的错误处理和状态报告
- 模块化设计，支持独立运行或完整流程
- 统一的配置管理
- 彩色终端输出，提升可读性
- **Web在线建模平台**：提供基于 FastAPI 的 Web 服务，支持文件上传、实时日志查看和结果下载
- **实时日志推送**：通过 WebSocket 实时推送建模过程中的日志信息
- **任务管理**：支持多客户端连接，自动管理建模任务队列

## 系统要求

- Python 3.6+
- 依赖包：
  - paramiko (SSH/SFTP 客户端)
  - colorama (终端彩色输出)
  - fastapi (Web 框架，用于在线建模服务)
  - uvicorn (ASGI 服务器，用于运行 FastAPI 应用)
  - python-multipart (文件上传支持)
  - jinja2 (模板引擎)

## 安装

1. 克隆仓库：
```bash
git clone <repository-url>
cd windchill-remote-tools
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

## 配置

编辑 `windchill_config.py` 文件配置连接信息：

```python
# SSH连接配置
SSH_CONFIG = {
    'hostname': 'your-server.com',  # 服务器地址
    'username': 'your-username',    # SSH用户名
    'password': 'your-password',    # SSH密码
    'port': 22,                     # SSH端口
    'timeout': 60                   # 超时时间(秒)
}

# Windchill环境配置
WINDCHILL_CONFIG = {
    'wt_home': '/path/to/windchill',  # Windchill安装目录
    'local_base': 'dist',             # 下载文件的本地基目录
    'local_root': 'model'             # 上传文件的本地根目录
}

# 要处理的模型类列表
MODEL_CLASSES = [
    'ext.app.process.model.YourModel',
    # 添加更多模型类...
]
```

## 使用方法

### 1. 独立运行各个工具

准备远程目录：
```bash
python remote_modeling_prepare.py
```

上传模型文件：
```bash
python remote_modeling_upload.py
```

生成代码和SQL：
```bash
python remote_modeling_generator.py
```

收集生成的文件：
```bash
python remote_modeling_collector.py
```

### 2. 运行完整流程

执行完整的建模流程（按顺序执行所有步骤）：
```bash
python remote_modeling_pipeline.py
```

### 3. 启动Web在线建模服务

启动基于 FastAPI 的 Web 服务，提供在线建模功能：
```bash
python modeling_server.py
```

服务启动后，访问 `http://localhost:8000` 即可使用 Web 界面进行建模操作。

**Web服务功能：**
- 通过浏览器上传模型文件
- 实时查看建模日志
- 下载建模结果（ZIP格式）
- 支持多任务管理

## 工具说明

### remote_modeling_prepare.py
- 功能：创建必要的远程目录结构
- 为每个模型类创建 src、src_gen、codebase 和 db/sql3 目录

### remote_modeling_upload.py
- 功能：上传模型文件到服务器
- 支持递归上传
- 自动创建远程目录

### remote_modeling_generator.py
- 功能：生成模型相关的代码和SQL
- 执行 Windchill ant 任务
- 支持批量处理多个模型类

### remote_modeling_collector.py
- 功能：下载生成的文件到本地
- 保持远程目录结构
- 彩色输出下载状态

### remote_modeling_pipeline.py
- 功能：串联所有操作的主入口
- 按顺序执行所有步骤
- 出错时立即停止并报告

### modeling_server.py
- **功能**：提供基于 FastAPI 的 Web 在线建模服务
- **主要特性**：
  - Web 界面：提供友好的 Web 界面进行建模操作
  - 文件上传：支持通过 HTTP POST 上传模型文件（支持多文件）
  - 实时日志：通过 WebSocket 实时推送建模过程中的日志信息
  - 任务管理：自动生成任务ID，支持多客户端连接，同一时间只允许一个任务执行
  - 结果下载：将建模结果打包为 ZIP 文件供用户下载
  - 日志记录：所有操作日志自动保存到 `modeling.log` 文件
- **API端点**：
  - `GET /`：Web 主页界面
  - `POST /upload`：上传模型文件（需要 client_id 和 task_id 参数）
  - `GET /download`：下载建模结果（需要 task_id 参数）
  - `GET /create_task`：创建新任务，返回任务ID
  - `WebSocket /ws`：WebSocket 连接，用于实时日志推送和任务控制
- **工作流程**：
  1. 客户端通过 WebSocket 连接获取 client_id
  2. 调用 `/create_task` 创建任务，获取 task_id
  3. 通过 `/upload` 上传模型文件
  4. 通过 WebSocket 发送建模指令（action: "modeling"）
  5. 服务器自动解析上传的文件，提取 Java 类路径
  6. 执行建模流程，实时推送日志
  7. 建模完成后，通过 `/download` 下载结果
- **技术实现**：
  - 使用 FastAPI 构建 RESTful API 和 WebSocket 服务
  - 自定义标准输出流，实现日志的实时推送和文件记录
  - 异步任务处理，避免阻塞事件循环
  - 自动任务隔离，每个任务使用独立的目录结构

## 错误处理

- 所有工具都提供详细的错误信息
- 完整流程中任何步骤失败都会立即停止
- 错误信息包含具体的失败原因和位置

## 注意事项

1. 确保 SSH 连接信息正确
2. 确保 Windchill 环境配置正确
3. 本地目录需要有写入权限
4. 建议先小规模测试再处理大量文件

## 开发计划

- [ ] 添加进度条显示
- [ ] 支持文件过滤（按日期/类型）
- [ ] 添加 MD5 校验
- [ ] 实现增量上传
- [x] 添加日志记录功能（已实现）
- [x] Web在线建模服务（已实现）

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License 