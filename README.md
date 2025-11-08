# Windchill 远程建模工具集

这是一套用于 Windchill 远程建模的工具集，支持通过 SSH/SFTP 远程执行 Windchill 建模相关的操作。工具集包含以下功能：

- 远程目录准备
- 模型文件上传
- 代码和SQL生成
- 生成文件收集

## 功能特点

- 基于 SSH/SFTP 的远程操作
- 支持批量处理多个模型类
- 完整的错误处理和状态报告
- 模块化设计，支持独立运行或完整流程
- 统一的配置管理
- 彩色终端输出，提升可读性

## 系统要求

- Python 3.6+
- 依赖包：
  - paramiko (SSH/SFTP 客户端)
  - colorama (终端彩色输出)

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
- [ ] 添加日志记录功能

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License 