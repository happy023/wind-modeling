import os
import re
import json
import asyncio
import sys
import zipfile
import tempfile
import threading
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.websockets import WebSocket, WebSocketDisconnect
from typing import List, Dict

from fastapi import Query
from starlette.responses import PlainTextResponse

import remote_modeling_pipeline
from remote_modeling_config import MODELING_CONFIG
from remote_modeling_executor import detect_log_level, log
from modeling_read_classname import get_java_class_full_path

# 配置
LOG_FILE = Path("../modeling.log")

# ANSI / 控制台颜色码（前端无法渲染，会显示成 []0m 之类空噪声）
_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# 确保日志文件以 UTF-8 编码打开
sys.stdout.reconfigure(encoding='utf-8')  # 配置标准输出编码
sys.stderr.reconfigure(encoding='utf-8')  # 配置标准错误编码

# 初始化FastAPI应用
app = FastAPI(title="Windchill拉模在线建模系统", description="支持文件上传、实时日志和结果下载的在线建模平台")

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 模板
templates = Jinja2Templates(directory=".")


class _CaptureStream:
    """把 stdout/stderr 透传控制台，同时按行清洗后推到 WebSocket。"""

    def __init__(self, manager: "ConnectionManager", original):
        self._manager = manager
        self._original = original

    def write(self, message: str):
        if not isinstance(message, str):
            message = str(message)
        self._original.write(message)
        self._manager.capture_for_clients(message)

    def flush(self):
        self._original.flush()
        self._manager.flush_log_file()

    def __getattr__(self, name):
        return getattr(self._original, name)


# 连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}  # ID -> WebSocket
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.log_file = open(LOG_FILE, "a", encoding="utf-8")
        self.loop = None
        self._line_buf = ""  # 按行聚合，避免 print/colorama 多次 write 产生空行
        self._buf_lock = threading.Lock()

        # 捕获 stdout + stderr（pipeline 的 log() 走 stderr）
        sys.stdout = _CaptureStream(self, self.original_stdout)
        sys.stderr = _CaptureStream(self, self.original_stderr)

        self.working_client_id = ""

    def __del__(self):
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        self.log_file.close()

    @staticmethod
    def _strip_ansi(text: str) -> str:
        return _ANSI_RE.sub("", text)

    def flush_log_file(self):
        self.log_file.flush()

    def capture_for_clients(self, message: str):
        """清洗 ANSI、按行缓冲，再写入日志文件并推送到前端。"""
        with self._buf_lock:
            self._line_buf += message.replace("\r\n", "\n").replace("\r", "\n")
            while "\n" in self._line_buf:
                line, self._line_buf = self._line_buf.split("\n", 1)
                self._emit_line(line)

    def _emit_line(self, line: str):
        clean = self._strip_ansi(line).strip()
        if not clean:
            return

        level = detect_log_level(clean)
        level_tag = {
            "success": "OK",
            "error": "ERR",
            "warning": "WARN",
            "info": "INFO",
        }.get(level, "INFO")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_file.write(f"[{timestamp}] [{level_tag}] {clean}\n")

        self._send_to_websocket(clean, level)

    def _send_to_websocket(self, message: str, level: str = "info"):
        # 获取当前事件循环
        if self.loop is None:
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                # 没有运行的事件循环（例如在启动时）
                return

        # 在事件循环中调度异步任务
        self.loop.call_soon_threadsafe(
            asyncio.create_task,
            self.send_log(self.working_client_id, message, level)
        )

    async def send_log(self, client_id: str, message: str, level: str = "info"):
        if len(self.active_connections) == 0:
            return

        clean = self._strip_ansi(message).strip()
        if not clean:
            return

        resolved = level if level in ("success", "error", "warning", "info") else detect_log_level(clean)
        log_entry = {
            "type": "log",
            "level": resolved,
            "message": clean
        }
        log_json = json.dumps(log_entry, ensure_ascii=False)
        await self.send_to_client(client_id, log_json)

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        self.active_connections.pop(client_id, None)

    async def send_to_client(self, client_id: str, message: str):
        if client_id not in self.active_connections:
            return
        try:
            await self.active_connections[client_id].send_text(message)
        except Exception as e:
            # 打印到原始标准输出，避免递归调用
            self.original_stdout.write(f"WebSocket发送失败: {e}\n")

    async def send_status(self, client_id: str, status: str):
        status_entry = {
            "type": "status",
            "status": status
        }
        status_json = json.dumps(status_entry)
        await self.send_to_client(client_id, status_json)

    # 运行建模脚本
    async def run_modeling_script(self, client_id: str, task_id: str):
        if len(self.working_client_id) > 0:
            await self.send_log(
                client_id,
                f"当前有其它客户端在执行任务（ID: {self.working_client_id}）",
                "warning",
            )
            await self.send_status(client_id, "finished")
            return

        try:
            self.working_client_id = client_id

            await self.send_status(client_id, "started")

            # 按任务拼路径，不要改全局 MODELING_CONFIG（否则第二次会叠成 ../dist/task1/task2）
            task_config = {
                **MODELING_CONFIG,
                "local_base": os.path.join(MODELING_CONFIG["local_base"], task_id),
                "local_root": os.path.join(MODELING_CONFIG["local_root"], task_id),
            }
            model_classes: List[str] = []

            model_dir = os.path.abspath(task_config["local_root"])
            log(f"模型目录: {model_dir}")

            # 遍历当前目录下的所有文件和子目录
            for root, dirs, files in os.walk(model_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    log(f"读取文件: {file_path}")
                    # 将上传的类名加到模型配置
                    class_name = get_java_class_full_path(str(file_path))
                    log(f"解析到类路径: {class_name}")
                    model_classes.append(class_name)

            if not model_classes:
                log(f"模型目录为空或未解析到类: {model_dir}", "error")
                await self.send_log(
                    client_id,
                    f"建模出错：未找到可建模的 Java 类（目录: {model_dir}）",
                    "error",
                )
                await self.send_status(client_id, "finished")
                return

            log(f"开始执行建模脚本，任务ID: {self.working_client_id}，类数: {len(model_classes)}")
            # 同步调用会阻塞事件循环；注入本次任务配置，避免污染全局
            ok, err = await asyncio.to_thread(
                remote_modeling_pipeline.modeling,
                model_classes,
                None,
                task_config,
            )
            if ok:
                log("建模任务全部完成", "success")
            else:
                log(f"建模任务失败: {err}", "error")
                await self.send_log(client_id, f"建模失败: {err}", "error")
            await self.send_status(client_id, "finished")

        except Exception as e:
            log(f"建模过程中发生错误: {str(e)}", "error")
            await self.send_status(client_id, "finished")
        finally:
            log("清理建模任务状态")
            self.working_client_id = ""


manager = ConnectionManager()


# 主页
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("static/index.html", {"request": request})


# 文件上传端点
@app.post("/upload")
async def upload_files(client_id: str = Form(...), task_id: str = Form(...),
                       files: List[UploadFile] = File(..., max_length=1 * 1024 * 1024)):
    if client_id.isspace():
        raise HTTPException(status_code=500, detail="客户端id不能为空")
    if task_id.isspace():
        raise HTTPException(status_code=500, detail="任务id不能为空")

    model_dir = Path("../model") / task_id
    model_dir.mkdir(exist_ok=True)

    await manager.send_log(client_id, f"开始上传文件到任务 {task_id}，目录 {model_dir}")

    try:
        # 保存上传的文件
        for file in files:
            file_path = model_dir / file.filename
            with open(file_path, "wb") as f:
                f.write(await file.read())
            await manager.send_log(client_id, f"已上传文件: {file.filename}", "success")

        await manager.send_log(client_id, "所有文件上传完成", "success")

        return {"status": "success", "task_id": task_id, "message": "文件上传成功"}

    except Exception as e:
        manager.original_stdout.write(f"上传过程中发生错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"上传过程中发生错误: {str(e)}")


# 下载结果
@app.get("/download")
async def download_results(task_id: str = Query(None, description="任务id")):
    # 创建临时zip文件
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
        zip_path = temp_zip.name

    dist_dir = Path("../dist") / task_id
    # 将结果目录打包为zip
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, dist_dir))

    # 返回zip文件
    response = FileResponse(
        path=zip_path,
        filename=f"modeling_results_{task_id}.zip",
        media_type='application/zip'
    )

    # 设置响应头，让浏览器知道这是一个下载文件
    response.headers[
        "Content-Disposition"] = f"attachment; filename=modeling_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    # 删除临时文件（响应发送后）
    async def cleanup():
        await asyncio.sleep(1)  # 确保文件已被发送
        os.remove(zip_path)

    asyncio.create_task(cleanup())

    return response


@app.get("/create_task")
async def create_task():
    # 生成任务id
    task_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    # 准备目录
    (Path("../dist") / task_id).mkdir(exist_ok=True)
    return PlainTextResponse(content=task_id, media_type="text/plain")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # 为每个连接生成唯一 ID
    client_id = str(uuid4())
    await manager.connect(websocket, client_id)  # 将 ID 和 WebSocket 关联
    await websocket.send_text(json.dumps({
        "type": 'clientId',
        "clientId": client_id
    }))
    try:
        while True:
            data = await websocket.receive_text()
            manager.original_stdout.write(f"客户端 {client_id} 发送消息: {data}")
            dict_data = json.loads(data)
            if dict_data["action"] != "modeling":
                continue

            task_id = dict_data["task_id"]
            # 异步调用建模脚本
            if task_id.isspace():
                await manager.send_log(client_id, "建模出错：缺少参数，任务id为空", "error")
                continue

            # asyncio.create_task(manager.run_modeling_script(client_id, task_id))
            await manager.run_modeling_script(client_id, task_id)

    except WebSocketDisconnect:
        manager.disconnect(client_id)  # 通过 ID 断开连接
        if manager.working_client_id == client_id:
            manager.working_client_id = ""
        log(f"客户端 {client_id} 已断开", "warning")


# 启动应用
if __name__ == "__main__":
    import uvicorn

    log("==== Windchill拉模在线建模系统 ====")
    log("==== http://wind-modeling.okcode.cn/ ====")
    log(f"日志文件: {LOG_FILE.absolute()}")
    log("=" * 40)

    uvicorn.run(app, host="0.0.0.0", port=8000)
