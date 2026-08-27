"""
Windchill远程建模工具的主入口脚本
按顺序执行: 准备目录 -> 上传模型 -> 生成代码 -> 收集结果

无参调用时行为与原先一致（读 remote_modeling_config）。
可选参数用于外部（如 windchill-cli）注入配置，不改变独立脚本用法。
"""

from __future__ import annotations

import sys
from typing import List, Optional, Tuple

from remote_modeling_executor import log

import remote_modeling_prepare
import remote_modeling_upload
import remote_modeling_generator
import remote_modeling_collector


def modeling(
    model_classes: Optional[List[str]] = None,
    ssh_config: Optional[dict] = None,
    modeling_config: Optional[dict] = None,
) -> Tuple[bool, Optional[str]]:
    """执行完整的建模流程。

    Returns:
        (是否成功, 错误信息)。命令行 ``__main__`` 仍会在失败时 sys.exit(1)。
    """
    try:
        log("开始 Windchill 远程建模流程...")

        kwargs = {
            "model_classes": model_classes,
            "ssh_config": ssh_config,
            "modeling_config": modeling_config,
        }

        success, error = remote_modeling_prepare.prepare_directories(**kwargs)
        if not success:
            log(f"准备目录失败: {error}")
            return False, error
        log("目录准备完成")

        success, error = remote_modeling_upload.upload_models(**kwargs)
        if not success:
            log(f"上传模型失败: {error}")
            return False, error
        log("模型上传完成")

        success, error = remote_modeling_generator.generate_code(**kwargs)
        if not success:
            log(f"生成代码失败: {error}")
            return False, error
        log("代码生成完成")

        success, error = remote_modeling_collector.collect_files(**kwargs)
        if not success:
            log(f"收集结果失败: {error}")
            return False, error
        log("结果收集完成")
        log("所有操作已完成")
        return True, None
    except Exception as e:
        log(f"建模流程异常: {e}")
        return False, str(e)


if __name__ == "__main__":
    ok, err = modeling()
    if not ok:
        sys.exit(1)
