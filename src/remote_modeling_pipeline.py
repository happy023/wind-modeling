"""
Windchill远程建模工具的主入口脚本
按顺序执行: 准备目录 -> 上传模型 -> 生成代码 -> 收集结果
"""

import sys
import remote_modeling_prepare
import remote_modeling_upload
import remote_modeling_generator
import remote_modeling_collector

def modeling():
    """执行完整的建模流程"""
    print("🚀 开始Windchill远程建模流程...")
    
    # 1. 准备目录
    success, error = remote_modeling_prepare.prepare_directories()
    if not success:
        print(f"❌ 准备目录失败: {error}")
        sys.exit(1)
    print("✅ 目录准备完成")

    # 2. 上传模型
    success, error = remote_modeling_upload.upload_models()
    if not success:
        print(f"❌ 上传模型失败: {error}")
        sys.exit(1)
    print("✅ 模型上传完成")

    # 3. 生成代码
    success, error = remote_modeling_generator.generate_code()
    if not success:
        print(f"❌ 生成代码失败: {error}")
        sys.exit(1)
    print("✅ 代码生成完成")

    # 4. 收集结果
    success, error = remote_modeling_collector.collect_files()
    if not success:
        print(f"❌ 收集结果失败: {error}")
        sys.exit(1)
    print("✅ 结果收集完成")

    print("\n🎉 所有操作已完成!")


if __name__ == "__main__":
    modeling()