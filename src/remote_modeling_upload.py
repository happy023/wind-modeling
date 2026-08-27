"""
Windchill远程文件上传工具
用于上传模型文件到服务器
"""

import os
import paramiko
from typing import List, Tuple, Optional
from remote_modeling_config import SSH_CONFIG, MODELING_CONFIG, MODEL_CLASSES
from remote_modeling_platform import (
    detect_platform,
    ensure_sftp_dir,
    join_remote,
    norm_remote,
    normalize_platform,
)


class WindchillSFTPUploader:
    def __init__(self, hostname: str, username: str, password: str,
                 wt_home: str, local_root: str, platform: Optional[str] = None):
        """
        Windchill文件上传工具

        :param host: Linux服务器地址
        :param user: SSH用户名
        :param pwd: SSH密码
        :param wt_home: Windchill主目录(如/home/windchill/windchill_11.0 或 C:/ptc/Windchill)
        :param local_root: 本地文件根目录(用于计算相对路径)
        :param platform: 远程服务器平台 'linux' / 'windows'；None 自动探测
        """
        self.hostname = hostname
        self.username = username
        self.password = password
        self.wt_home = str(wt_home)
        self.local_root = os.path.expanduser(local_root)
        self.platform = normalize_platform(platform)
        self.ssh = None
        self.sftp = None

    def connect(self) -> bool:
        """建立SFTP连接"""
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(
                hostname=self.hostname,
                username=self.username,
                password=self.password,
                timeout=10
            )
            # 未显式指定平台时自动探测，并按平台规范化远程 wt_home
            if self.platform is None:
                self.platform = detect_platform(self.ssh)
            print(f"远程服务器平台: {self.platform}")
            self.wt_home = norm_remote(self.wt_home, self.platform)
            self.sftp = self.ssh.open_sftp()
            return True
        except Exception as e:
            print(f"连接失败: {str(e)}")
            return False

    def _get_remote_path(self, local_path: str, class_path: str) -> str:
        """
        根据本地路径计算远程路径，保持相对结构

        示例:
        本地: ~/windchill_uploads/bin/start.sh
        wt_home: /home/windchill/windchill_11.0
        远程: /home/windchill/windchill_11.0/bin/start.sh
        """
        # 获取相对于本地根目录的路径
        rel_path = os.path.relpath(local_path, self.local_root)
        remote_path = join_remote(
            self.wt_home, class_path, rel_path, platform=self.platform
        )

        print(f"远程路径:{remote_path}")

        return remote_path

    def _ensure_remote_dir(self, remote_path: str):
        """确保远程目录存在（跨平台，含 Windows 根目录判断）"""
        ensure_sftp_dir(self.sftp, remote_path, self.platform)

    def upload(self, local_path: str, class_path: str, recursive: bool = False) -> Tuple[bool, str]:
        """
        上传文件或目录

        :param local_path: 本地路径(绝对路径或相对于local_root的路径)
        :param recursive: 如果是目录，是否递归上传
        :return: (成功状态, 远程路径或错误信息)
        """
        if not self.sftp:
            return False, "SFTP连接未建立"

        try:
            # 处理相对路径
            if not os.path.isabs(local_path):
                local_path = os.path.join(self.local_root, local_path)

            local_path = os.path.normpath(local_path)

            print(f"本地路径：{local_path}")

            if os.path.isdir(local_path):
                return self._upload_dir(local_path, class_path, recursive)
            return self._upload_file(local_path, class_path)
        except Exception as e:
            return False, f"上传失败: {str(e)}"

    def _upload_file(self, local_file: str, class_path: str) -> Tuple[bool, str]:
        """上传单个文件"""
        remote_file = self._get_remote_path(local_file, class_path)
        self._ensure_remote_dir(remote_file)
        self.sftp.put(local_file, remote_file)
        return True, remote_file

    def _upload_dir(self, local_dir: str, class_path: str, recursive: bool) -> Tuple[bool, str]:
        """上传整个目录"""
        remote_dir = self._get_remote_path(local_dir, class_path)

        # 创建远程目录
        try:
            self.sftp.stat(remote_dir)
        except IOError:
            self.sftp.mkdir(remote_dir)

        uploaded_files = []
        for item in os.listdir(local_dir):
            local_path = os.path.join(local_dir, item)
            if os.path.isdir(local_path):
                if recursive:
                    success, path = self._upload_dir(local_path, class_path, recursive)
                    uploaded_files.append((success, path))
            else:
                success, path = self._upload_file(local_path, class_path)
                uploaded_files.append((success, path))

        # 返回目录路径和上传的文件数
        success_count = sum(1 for s, _ in uploaded_files if s)
        return (True, f"{remote_dir} (上传了 {success_count}/{len(uploaded_files)} 个文件)")

    def close(self):
        """关闭连接"""
        if self.sftp:
            self.sftp.close()
        if self.ssh:
            self.ssh.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def upload_models(
    model_classes: Optional[List[str]] = None,
    ssh_config: Optional[dict] = None,
    modeling_config: Optional[dict] = None,
) -> Tuple[bool, Optional[str]]:
    """
    上传模型文件的主函数

    可选参数用于外部注入配置；缺省时行为与原先完全一致。

    Returns:
        Tuple[bool, Optional[str]]: (是否成功, 错误信息)
    """
    ssh = ssh_config or SSH_CONFIG
    mc = modeling_config or MODELING_CONFIG
    classes = MODEL_CLASSES if model_classes is None else model_classes

    with WindchillSFTPUploader(
            hostname=ssh['hostname'],
            username=ssh['username'],
            password=ssh['password'],
            wt_home=mc['wt_home'],
            local_root=mc['local_root'],
            platform=normalize_platform(ssh.get('platform'))
    ) as uploader:
        print(f"已连接到 {ssh['hostname']}")

        for model_class in classes:
            class_path, class_name = model_class.rsplit('.', 1)
            local_file = f'{class_name}.java'
            print(f"正在上传: {local_file}")
            success, result = uploader.upload(local_file, 'src/' + class_path.replace('.', '/'), recursive=True)

            if not success:
                return False, f"上传失败: {result}"
            print(f"上传成功 -> 远程位置: {result}")

        return True, None


if __name__ == "__main__":
    success, error = upload_models()
    if not success:
        print(f"上传模型失败: {error}")
        exit(1)
    print("上传任务完成")

# 高级功能扩展建议:
# 1. 添加进度条显示
# 2. 支持文件过滤(按日期/类型)
# 3. 添加MD5校验
# 4. 实现增量上传(只上传修改过的文件)
# 5. 添加日志记录功能
