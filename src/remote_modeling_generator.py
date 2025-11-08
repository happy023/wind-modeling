"""
Windchill远程代码生成工具
用于生成模型相关的代码和SQL
"""

import paramiko
import re
import time
from typing import List, Tuple, Optional
from remote_modeling_config import SSH_CONFIG, MODELING_CONFIG, MODEL_CLASSES


class SmartWindchillExecutor:
    def __init__(self, hostname: str, username: str, password: str,
                 wt_home: str, port: int = 22, timeout: int = 30):
        """
        改进版Windchill执行器，自动检测命令完成

        :param timeout: 全局超时时间(秒)
        """
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.wt_home = wt_home
        self.timeout = timeout
        self.client = None
        self.shell = None
        self.prompt_pattern = re.compile(r'wt\>\>|[\$#]\s*$')  # 匹配Windchill或系统提示符
        self.command_end_markers = [
            self.prompt_pattern,
            re.compile(r'Command completed'),  # Windchill常见完成消息
            re.compile(r'ERROR|Exception')  # 错误标识
        ]

    def connect(self) -> bool:
        """建立连接并初始化Windchill环境"""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                hostname=self.hostname,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=self.timeout
            )

            self.shell = self.client.invoke_shell()
            self.shell.settimeout(1)  # 设置较小的接收超时以便轮询

            # 初始化Windchill环境
            self._send_and_wait(f'export WT_HOME={self.wt_home}')
            response = self._send_and_wait(f'{self.wt_home}/bin/windchill shell')

            # 从响应中更新提示符模式
            if 'wt>>' in response:
                self.prompt_pattern = re.compile(r'wt\>\>\s*$')

            return True

        except Exception as e:
            print(f"连接失败: {str(e)}")
            self.close()
            return False

    def _send_and_wait(self, command: str, timeout: Optional[int] = None) -> str:
        """发送命令并等待直到检测到完成"""
        if not self.shell:
            raise RuntimeError("SSH连接未建立")

        timeout = timeout or self.timeout
        end_time = time.time() + timeout
        self.shell.send(command + '\n')

        output = ""
        while time.time() < end_time:
            if self.shell.recv_ready():
                data = self.shell.recv(4096).decode('utf-8')
                output += data

                # 检查是否出现完成标记
                if any(marker.search(data) for marker in self.command_end_markers):
                    break
            else:
                time.sleep(0.1)

        return output

    def execute_command(self, command: str, timeout: Optional[int] = None) -> Tuple[bool, str]:
        """执行单个命令并返回清理后的输出"""
        try:
            raw_output = self._send_and_wait(command, timeout)

            # 清理输出: 移除命令回显和最后的提示符
            cleaned = []
            for line in raw_output.split('\n'):
                if line.strip() not in (command.strip(), '') and not self.prompt_pattern.search(line):
                    cleaned.append(line)
            msg = '\n'.join(cleaned).strip()

            print(f"{'🟢执行成功' if ('BUILD FAILED' not in msg) else '🔴执行失败'},命令 {command}")
            print(msg)

            return True, msg

        except Exception as e:
            error = f"🔴执行出错: {str(e)}，命令 {command}"
            return False, error

    def execute_commands(self, commands: List[str]) -> List[Tuple[bool, str]]:
        """执行多个命令"""
        return [self.execute_command(cmd) for cmd in commands]

    def close(self):
        """安全关闭连接"""
        try:
            if hasattr(self, 'shell') and self.shell:
                self.shell.close()
            if hasattr(self, 'client') and self.client:
                self.client.close()
        except:
            pass
        finally:
            self.shell = None
            self.client = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def generate_code() -> Tuple[bool, Optional[str]]:
    """
    生成代码和SQL的主函数
    
    Returns:
        Tuple[bool, Optional[str]]: (是否成功, 错误信息)
    """
    with SmartWindchillExecutor(
            hostname=SSH_CONFIG['hostname'],
            username=SSH_CONFIG['username'],
            password=SSH_CONFIG['password'],
            wt_home=MODELING_CONFIG['wt_home'],
            port=SSH_CONFIG['port'],
            timeout=SSH_CONFIG['timeout']
    ) as executor:
        success, status = executor.execute_command('cd $WT_HOME')
        if not success:
            print(f"进入Windchill目录失败: {status}")
            return False, "进入Windchill目录失败"

        # 批量执行命令
        commands = []
        # 先执行class生成
        # for model_class in MODEL_CLASSES:
        #     class_path = model_class.replace('.', '/')
        #     commands.extend([
        #         f'ant -f bin/tools.xml class -Dclass.includes={class_path}.java -Dencoding=utf-8',
        #     ])
        #
        # # 再执行sql生成
        # for model_class in MODEL_CLASSES:
        #     commands.extend([
        #         f'ant -f bin/tools.xml sql_script -Dgen.input={model_class} -Dencoding=utf-8'
        #     ])

        # 上面的方式在某些情况下不适合，比如存在相互依赖的模型，需要使用下面的方式
        for model_class in MODEL_CLASSES:
            class_path = model_class.replace('.', '/')
            package_path, class_name = class_path.rsplit('/', 1)
            # ant -f bin/tools.xml class -Dclass.includes=ext/app/processautoconfig/model/*.java
            commands.append(f'ant -f bin/tools.xml class -Dclass.includes={package_path}/*.java -Dencoding=utf-8')

        for model_class in MODEL_CLASSES:
            package_path, class_name = model_class.rsplit('.', 1)
            # ant -f bin/tools.xml sql_script -Dgen.input=ext.app.processautoconfig.model.* -Dencoding=utf-8
            commands.append(f'ant -f bin/tools.xml sql_script -Dgen.input={package_path}.* -Dencoding=utf-8')
        # 去重
        commands = list(dict.fromkeys(commands))

        for i, (cmd_success, cmd_output) in enumerate(executor.execute_commands(commands)):
            if not cmd_success:
                return False, f"生成失败: {commands[i]}\n{cmd_output}"
        return True, None


if __name__ == "__main__":
    success, error = generate_code()
    if not success:
        print(f"❌ 生成代码失败: {error}")
        exit(1)
    print("✅ 代码生成完成")
