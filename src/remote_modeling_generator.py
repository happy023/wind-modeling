"""
Windchill远程代码生成工具
用于生成模型相关的代码和SQL
"""

from typing import List, Optional, Tuple
from remote_modeling_config import SSH_CONFIG, MODELING_CONFIG, MODEL_CLASSES
from remote_modeling_executor import SmartWindchillExecutor, log
from remote_modeling_platform import (
    ant_tools_path,
    cd_wt_home_cmd,
    is_windows,
    norm_remote,
    normalize_platform,
)


def generate_code(
    model_classes: Optional[List[str]] = None,
    ssh_config: Optional[dict] = None,
    modeling_config: Optional[dict] = None,
) -> Tuple[bool, Optional[str]]:
    """
    生成代码和SQL的主函数

    可选参数用于外部注入配置；缺省时行为与原先完全一致。

    Returns:
        Tuple[bool, Optional[str]]: (是否成功, 错误信息)
    """
    ssh = ssh_config or SSH_CONFIG
    mc = modeling_config or MODELING_CONFIG
    classes = MODEL_CLASSES if model_classes is None else model_classes

    with SmartWindchillExecutor(
            hostname=ssh['hostname'],
            username=ssh['username'],
            password=ssh['password'],
            wt_home=mc['wt_home'],
            port=ssh['port'],
            timeout=ssh['timeout'],
            platform=normalize_platform(ssh.get('platform'))
    ) as executor:
        # 用连接后（可能已自动探测）的平台生成命令
        platform = executor.platform
        # Windows：cd 已由 execute_windchill 管道内的 cd /d 处理，这里跳过
        if not is_windows(platform):
            success, status = executor.execute_command(cd_wt_home_cmd(mc['wt_home'], platform))
            if not success:
                log(f"进入Windchill目录失败: {status}", "error")
                return False, "进入Windchill目录失败"

        # 批量执行命令
        tools = ant_tools_path(platform)
        # Windows：ant 用 Windchill 自带 ant（windchill shell 环境已配好 JDK）
        ant_prefix = (
            f'"{norm_remote(mc["wt_home"], platform)}\\ant\\bin\\ant.bat"'
            if is_windows(platform) else 'ant'
        )
        commands = []
        # 上面的方式在某些情况下不适合，比如存在相互依赖的模型，需要使用下面的方式
        for model_class in classes:
            class_path = model_class.replace('.', '/')
            package_path, class_name = class_path.rsplit('/', 1)
            # ant -f bin/tools.xml class -Dclass.includes=ext/app/processautoconfig/model/*.java
            commands.append(f'{ant_prefix} -f {tools} class -Dclass.includes={package_path}/*.java -Dencoding=utf-8')

        for model_class in classes:
            package_path, class_name = model_class.rsplit('.', 1)
            # ant -f bin/tools.xml sql_script -Dgen.input=ext.app.processautoconfig.model.* -Dencoding=utf-8
            commands.append(f'{ant_prefix} -f {tools} sql_script -Dgen.input={package_path}.* -Dencoding=utf-8')
        # 去重
        commands = list(dict.fromkeys(commands))

        if is_windows(platform):
            # Windows：全部 ant 任务一次管道执行（windchill.exe shell 只启动一次）
            success, status = executor.execute_windchill(commands)
            if not success:
                return False, f"生成失败: {status}"
            return True, None

        for i, (cmd_success, cmd_output) in enumerate(executor.execute_commands(commands)):
            if not cmd_success:
                return False, f"生成失败: {commands[i]}\n{cmd_output}"
        return True, None


if __name__ == "__main__":
    success, error = generate_code()
    if not success:
        log(f"生成代码失败: {error}", "error")
        raise SystemExit(1)
    log("代码生成完成", "success")
