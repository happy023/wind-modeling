#!/bin/bash

# 启动Oracle监听和数据库
echo "启动Oracle监听和数据库..."
su - oracle -c "lsnrctl start"
su - oracle -c "sqlplus /nolog << EOF
conn / as sysdba
startup
exit
EOF"

# 检查Oracle监听状态
su - oracle -c "lsnrctl status"

# 启动Apache服务
echo "启动Apache服务..."
cd /ptc/Windchill_12.1/HTTPServer/bin
./apachectl start

# 启动DS服务
echo "启动DS服务..."
cd /ptc/Windchill_11.0/WindchillDS/server/bin
./start-ds

# 启动Windchill服务
echo "启动Windchill服务..."
cd /ptc/Windchill_12.1/Windchill/bin
./windchill shell <<EOF
cd ..
windchill start
exit
EOF

echo "所有服务启动完成，请检查各服务状态是否正常"

echo "打开常用目录..."
xdg-open "/ptc/Windchill_12.1/Windchill/tmp/dist" &
xdg-open "/ptc/Windchill_12.1/Windchill/logs" &