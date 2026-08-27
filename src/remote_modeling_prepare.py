"""
Windchill远程目录准备工具
用于创建必要的目录结构
"""

from typing import List, Optional, Tuple
from remote_modeling_config import SSH_CONFIG, MODELING_CONFIG, MODEL_CLASSES
from remote_modeling_executor import SmartWindchillExecutor, log
from remote_modeling_platform import (
    cd_wt_home_cmd,
    make_dir_cmds,
    normalize_platform,
    pwd_cmd,
)


def prepare_directories(
    model_classes: Optional[List[str]] = None,
    ssh_config: Optional[dict] = None,
    modeling_config: Optional[dict] = None,
) -> Tuple[bool, Optional[str]]:
    """
    准备远程目录结构的主函数

    可选参数用于外部注入配置；缺省时行为与原先完全一致（读本模块全局配置）。

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

        # 执行快速命令
        success, result = executor.execute_command(pwd_cmd(platform))
        log(f"当前目录: {'成功' if success else '失败'}")
        log(result)

        success, status = executor.execute_command(cd_wt_home_cmd(mc['wt_home'], platform))
        if success:
            log("已进入 WT_HOME:")
            log(status)
        else:
            log(f"进入 WT_HOME 失败: {status}")

        # 批量执行命令（ensure_dir_cmds 保证全部删除在前、创建在后；dict.fromkeys 去重保序）
        rel_paths = []
        for model_class in classes:
            package_path, class_name = model_class.replace('.', '/').rsplit("/", 1)
            rel_paths.extend([
                f'src/{package_path}',
                f'src_gen/{package_path}',
                f'codebase/{package_path}',
                f'db/sql3/{package_path}'
            ])
        commands = make_dir_cmds(mc['wt_home'], rel_paths, platform)
        command_list = list(dict.fromkeys(commands))
        for i, (cmd_success, cmd_output) in enumerate(executor.execute_commands(command_list)):
            if not cmd_success:
                return False, f"创建目录失败: {command_list[i]}"
        return True, None


if __name__ == "__main__":
    success, error = prepare_directories()
    if not success:
        log(f"准备目录失败: {error}")
        raise SystemExit(1)
    log("目录准备完成")
