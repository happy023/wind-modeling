import re
from pathlib import Path

def get_java_class_full_path(java_file_path: str) -> str:
    """
    读取 Java 文件，提取包名和类名，返回全路径（如 `com.example.MyClass`）。
    如果无包声明，则返回类名本身（如 `MyClass`）。
    """
    path = Path(java_file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {java_file_path}")

    # 1. 提取包名（跳过空行和注释）
    package_name = None
    with open(java_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("/*"):
                continue  # 跳过空行和注释
            # 匹配 package 语句
            match = re.match(r"^package\s+([a-zA-Z0-9_.]+)\s*;", line)
            if match:
                package_name = match.group(1)
                break  # 找到包名后停止
            else:
                break  # 非包声明行（可能是类定义）

    # 2. 提取类名（从文件内容或文件名）
    class_name = None
    # 方式1：从文件内容中提取类名（匹配 `public class Xxx`）
    with open(java_file_path, "r", encoding="utf-8") as f:
        content = f.read()
        class_match = re.search(
            r"public\s+(?:class|interface|enum)\s+([a-zA-Z0-9_]+)", content
        )
        if class_match:
            class_name = class_match.group(1)
    # 方式2：如果未匹配到，则使用文件名（去掉 .java）
    if not class_name:
        class_name = path.stem  # 去除后缀的文件名

    # 3. 组合全路径
    if package_name:
        return f"{package_name}.{class_name}"
    return class_name

# 测试
if __name__ == "__main__":
    java_file = "D:/gitee-me/py-tools/windchill/model/CustomParamMasterIteration.java"
    print(get_java_class_full_path(java_file))  # 输出如: com.example.MyClass