"""
Windchill远程操作工具的共享配置文件
"""

# SSH连接配置
SSH_CONFIG = {
    'hostname': '填写你建模用的windchill地址',
    'username': 'root',
    'password': 'root',
    'port': 22,
    'timeout': 60
}

# Windchill环境配置
WINDCHILL_CONFIG = {
    'wt_home': '/ptc/Windchill_11.0/Windchill',
    'local_base': '../dist',  # 用于下载的本地基目录
    'local_root': '../model'  # 用于上传的本地根目录
}

# 模型类配置
MODEL_CLASSES = [
    # 'ext.app.process.model.BOPExtObject',
    # 'ext.app.processautoconfig.model.AQRowItem',
    # 'ext.app.processautoconfig.model.CustomParamMasterKey',
    # 'ext.app.processautoconfig.model.CustomParamMasterIdentity',
    # 'ext.app.processautoconfig.model.CustomParamMaster',
    # 'ext.app.processautoconfig.model.CustomParam',
    # 'ext.app.processautoconfig.model.CustomParamRowItem',
    # 'ext.app.process.model.BOPTableConfig',
    # 'ext.app.process.model.BOPColumnConfig',
    # 'ext.gbom.colorpart.model.ColorItem',
    # 'ext.app.processautoconfig.model.ProcessConfigMethodMasterKey',
    # 'ext.app.processautoconfig.model.ProcessConfigMethodMasterIdentity',
    # 'ext.app.processautoconfig.model.ProcessConfigMethodMaster',
    # 'ext.app.processautoconfig.model.ProcessConfigMethod',
    # 'ext.app.processautoconfig.model.ProcessConfigMethodMasterIteration',

    # 'ext.app.processautoconfig.model.ProcessConfigSequenceMasterKey',
    # 'ext.app.processautoconfig.model.ProcessConfigSequenceMasterIdentity',
    # 'ext.app.processautoconfig.model.ProcessConfigSequenceMaster',
    # 'ext.app.processautoconfig.model.ProcessConfigSequence',
    # 'ext.app.processautoconfig.model.ProcessConfigSequenceMasterIteration',

    # 'com.hihonor.wieditor.model.InspectionStandardTable',
    'com.hihonor.wieditor.model.QualityStandardTable',
]

