import os
import json
import asyncio
import sys
import zipfile
import tempfile
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
from remote_modeling_config import MODEL_CLASSES, MODELING_CONFIG
from modeling_read_classname import get_java_class_full_path

# 配置
LOG_FILE = Path("../modeling.log")

# 确保日志文件以 UTF-8 编码打开
sys.stdout.reconfigure(encoding='utf-8')  # 配置标准输出编码
sys.stderr.reconfigure(encoding='utf-8')  # 配置标准错误编码

# 初始化FastAPI应用
app = FastAPI(title="Windchill拉模在线建模系统", description="支持文件上传、实时日志和结果下载的在线建模平台")

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 模板
templates = Jinja2Templates(directory=".")


# 连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}  # ID -> WebSocket
        self.original_stdout = sys.stdout  # 保存原始标准输出
        self.log_file = open(LOG_FILE, "a", encoding="utf-8")  # 以UTF-8打开日志文件
        self.loop = None  # 事件循环

        # 替换标准输出为自定义流
        sys.stdout = self

        self.working_client_id = ""

    def __del__(self):
        # 恢复原始标准输出
        sys.stdout = self.original_stdout
        self.log_file.close()

    def write(self, message: str):
        # 写入原始标准输出
        self.original_stdout.write(message)

        # 写入日志文件
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [INFO] {message}"
        self.log_file.write(log_line)

        # 发送到所有WebSocket客户端
        self._send_to_websocket(message)

    def flush(self):
        # 调用原始标准输出的flush方法
        self.original_stdout.flush()
        self.log_file.flush()

    def _send_to_websocket(self, message: str):
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
            self.send_log(self.working_client_id, message)
        )

    async def send_log(self, client_id: str, message: str):
        if len(self.active_connections) == 0:
            return

        if message == "\n" or message == "\r\n":
            return

        message = message.replace("\n", "<br>")

        log_entry = {
            "type": "log",
            "level": "info",
            "message": message.rstrip()  # 去除末尾换行符
        }
        log_json = json.dumps(log_entry)
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

    # 转发所有未知属性到原始标准输出
    def __getattr__(self, name):
        return getattr(self.original_stdout, name)

    # 运行建模脚本
    async def run_modeling_script(self, client_id: str, task_id: str):
        if len(self.working_client_id) > 0:
            await self.send_log(client_id, f"当前有其它客户端在执行任务（ID: {self.working_client_id}）")
            await self.send_status(client_id, "finished")
            return

        if len(MODEL_CLASSES) > 0:
            await self.send_log(client_id,
                                f"当前有其它客户端在执行任务,MODEL_CLASSES不为空（ID: {self.working_client_id}）")
            return

        try:
            self.working_client_id = client_id

            await self.send_status(client_id, "started")

            # 更新全局变量，后面拉莫会使用
            MODELING_CONFIG['local_base'] = MODELING_CONFIG['local_base'] + '/' + task_id
            MODELING_CONFIG['local_root'] = MODELING_CONFIG['local_root'] + '/' + task_id

            model_dir = os.path.abspath(MODELING_CONFIG['local_root'])
            print(f"模型目录：{model_dir}")

            # 遍历当前目录下的所有文件和子目录
            for root, dirs, files in os.walk(model_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    print(f"读取文件: {file_path}")
                    # 将上传的类名加到模型配置
                    class_name = get_java_class_full_path(str(file_path))
                    print(f"解析到类路径: {class_name}")
                    MODEL_CLASSES.append(class_name)

            print(f"开始执行建模脚本，任务ID: {self.working_client_id}")
            # 同步调用会阻塞事件循环
            # remote_modeling_pipeline.modeling()
            # 改成异步调用日志才能正常输出
            await asyncio.to_thread(remote_modeling_pipeline.modeling)
            print("建模任务全部完成")
            await self.send_status(client_id, "finished")

        except Exception as e:
            print(f"建模过程中发生错误: {str(e)}")
            await self.send_status(client_id, "finished")
        finally:
            print("清理模型清单")
            self.working_client_id = ""
            MODEL_CLASSES.clear()
            pass


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
            await manager.send_log(client_id, f"已上传文件: {file.filename}")

        await manager.send_log(client_id, f"所有文件上传完成")

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
                await manager.send_log(client_id, f"建模出错：缺少参数，任务id为空")
                continue

            # asyncio.create_task(manager.run_modeling_script(client_id, task_id))
            await manager.run_modeling_script(client_id, task_id)

    except WebSocketDisconnect:
        manager.disconnect(client_id)  # 通过 ID 断开连接
        if manager.working_client_id == client_id:
            manager.working_client_id = ""
        print(f"客户端 {client_id} 已断开")


# 启动应用
if __name__ == "__main__":
    import uvicorn

    print("==== Windchill拉模在线建模系统 ====")
    print("==== http://wind-modeling.okcode.cn/ ====")
    print(f"日志文件: {LOG_FILE.absolute()}")
    print("=" * 40)

    uvicorn.run(app, host="0.0.0.0", port=8000)
