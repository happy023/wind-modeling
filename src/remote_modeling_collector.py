"""
Windchill远程文件下载工具
用于下载生成的文件到本地
"""

import os
import paramiko
from typing import List, Optional, Tuple
from colorama import init, Fore, Back, Style
from remote_modeling_config import SSH_CONFIG, MODELING_CONFIG, MODEL_CLASSES
from remote_modeling_platform import (
    detect_platform,
    is_sftp_dir,
    join_remote,
    norm_remote,
    normalize_platform,
    remote_path_module,
)


class WindchillSFTPDownloader:
    def __init__(self, hostname: str, username: str, password: str,
                 wt_home: str, local_base: str, port: int = 22,
                 platform: Optional[str] = None):
        """
        Windchill SFTP文件下载工具

        :param hostname: 服务器地址
        :param username: SSH用户名
        :param password: SSH密码
        :param wt_home: 远程Windchill根目录(如/opt/ptc/Windchill 或 C:/ptc/Windchill)
        :param local_base: 本地存储基目录(如D:/src)
        :param port: SSH端口
        :param platform: 远程服务器平台 'linux' / 'windows'；None 自动探测
        """
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.platform = normalize_platform(platform)
        self.remote_mod = remote_path_module(self.platform)  # 探测后按实际平台重建
        self.wt_home = str(wt_home).strip()
        self.local_base = os.path.normpath(os.path.expanduser(local_base))
        self.ssh = None
        self.sftp = None

        print(f"下载目录：{self.local_base}")

    def connect(self) -> bool:
        """建立SFTP连接"""
        try:
            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(
                hostname=self.hostname,
                port=self.port,
                username=self.username,
                password=self.password
            )
            # 未显式指定平台时自动探测，并按平台重建远程路径模块与 wt_home
            if self.platform is None:
                self.platform = detect_platform(self.ssh)
            print(f"🖥️ 远程服务器平台: {self.platform}")
            self.remote_mod = remote_path_module(self.platform)
            self.wt_home = norm_remote(self.wt_home, self.platform)
            self.sftp = self.ssh.open_sftp()
            return True
        except Exception as e:
            print(f"连接失败: {str(e)}")
            return False

    def _ensure_local_dir(self, remote_path: str) -> str:
        """
        确保本地目录存在，返回对应的本地路径

        例如:
        远程路径: /opt/ptc/Windchill/bin/startup.sh
        WT_HOME: /opt/ptc/Windchill
        本地基目录: D:/src
        返回: D:/src/bin/startup.sh
        """
        # 获取相对于WT_HOME的路径（按远程平台分隔符），本地统一转 '/' 再拼接
        rel_path = self.remote_mod.relpath(remote_path, self.wt_home)
        rel_parts = [p for p in str(rel_path).replace('\\', '/').split('/') if p]
        local_path = os.path.join(self.local_base, *rel_parts)

        # 创建本地目录
        local_dir = os.path.dirname(local_path)
        os.makedirs(local_dir, exist_ok=True)

        return local_path

    def _is_dir(self, path: str) -> bool:
        """检查远程路径是否为目录（兼容 Windows sftp-server 模式位缺失）"""
        return is_sftp_dir(self.sftp, path)

    def download_file(self, remote_path: str) -> Tuple[bool, str]:
        """
        下载单个文件，保持目录结构

        :param remote_path: 远程文件绝对路径
        :return: (是否成功, 本地存储路径或错误信息)
        """
        if not self.sftp:
            return False, "SFTP连接未建立"

        local_path = ""
        try:
            if self._is_dir(remote_path):
                return False, f"路径是目录不是文件: {remote_path}"

            local_path = self._ensure_local_dir(remote_path)
            self.sftp.get(remote_path, local_path)
            return True, local_path
        except Exception as e:
            if os.path.exists(local_path):
                os.remove(local_path)  # 删除文件
                print(f"删除生成出错的临时文件 {local_path}")
            return False, f"下载失败: {str(e)}"

    def download_directory(self, remote_dir: str, recursive: bool = True) -> List[Tuple[bool, str]]:
        """
        下载整个目录，保持目录结构

        :param remote_dir: 远程目录路径
        :param recursive: 是否递归下载子目录
        :return: 下载结果列表[(是否成功, 路径或错误信息)]
        """
        if not self.sftp:
            return [(False, "SFTP连接未建立")]

        results = []
        try:
            for entry in self.sftp.listdir_attr(remote_dir):
                remote_path = join_remote(remote_dir, entry.filename, platform=self.platform)
                if self._is_dir(remote_path):
                    if recursive:
                        results.extend(self.download_directory(remote_path, recursive))
                else:
                    status, result = self.download_file(remote_path)
                    results.append((status, result))
            return results
        except Exception as e:
            return [(False, f"目录下载失败: {str(e)}")]

    def download_from_relative(self, rel_path: str) -> Tuple[bool, str]:
        """
        通过相对于WT_HOME的路径下载文件或目录

        :param rel_path: 相对于WT_HOME的路径(如"bin/startup.sh")
        :return: (是否成功, 本地存储路径或错误信息)
        """
        remote_path = join_remote(self.wt_home, rel_path.lstrip('/\\'), platform=self.platform)
        if self._is_dir(remote_path):
            return self.download_directory(remote_path)
        return self.download_file(remote_path)

    def close(self):
        """关闭连接"""
        if hasattr(self, 'sftp') and self.sftp:
            self.sftp.close()
        if hasattr(self, 'ssh') and self.ssh:
            self.ssh.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def collect_files(
    model_classes: Optional[List[str]] = None,
    ssh_config: Optional[dict] = None,
    modeling_config: Optional[dict] = None,
) -> Tuple[bool, Optional[str]]:
    """
    收集生成的文件的主函数

    可选参数用于外部注入配置；缺省时行为与原先完全一致。

    Returns:
        Tuple[bool, Optional[str]]: (是否成功, 错误信息)
    """
    ssh = ssh_config or SSH_CONFIG
    mc = modeling_config or MODELING_CONFIG
    classes = MODEL_CLASSES if model_classes is None else model_classes

    with WindchillSFTPDownloader(
        hostname=ssh['hostname'],
        username=ssh['username'],
        password=ssh['password'],
        wt_home=mc['wt_home'],
        local_base=mc['local_base'],
        port=ssh['port'],
        platform=normalize_platform(ssh.get('platform'))
    ) as downloader:
        init(autoreset=True)  # 自动重置颜色

        for model_class in classes:
            package_path, class_name = model_class.replace('.', '/').rsplit("/", 1)
            
            # 构建需要下载的文件列表
            remote_files = [
                f'src/{package_path}/{class_name}.java',
                f'src_gen/{package_path}/_{class_name}.java',
                f'codebase/{package_path}/{class_name}.ClassInfo.ser',
                f'codebase/{package_path}/{class_name}.class',
                f'codebase/{package_path}/_{class_name}.class',
                f'db/sql3/{package_path}/create_{class_name}_Table.sql',
                f'db/sql3/{package_path}/create_{class_name}_Index.sql',
                f'db/sql3/{package_path}/drop_{class_name}_Index.sql',
                f'db/sql3/{package_path}/drop_{class_name}_Table.sql',
                f'db/sql3/{package_path}/Make_pkg_model_Table.sql',
                f'db/sql3/{package_path}/Make_pkg_model_Index.sql',
                f'db/sql3/{package_path}/Drop_pkg_model_Table.sql',
                f'db/sql3/{package_path}/Drop_pkg_model_Index.sql'
            ]

            for remote_file in remote_files:
                success, result = downloader.download_from_relative(remote_file)
                if success:
                    print(Fore.GREEN + f"🟢下载 {remote_file}: 成功 - {result}")
                else:
                    # return False, f"下载失败: {remote_file} - {result}"
                    print(Fore.RED + f"❌下载 {remote_file}: 失败 - {result}")
        return True, None


if __name__ == "__main__":
    success, error = collect_files()
    if not success:
        print(f"❌ 收集文件失败: {error}")
        exit(1)
    print("✅ 文件收集完成")
