docker build . xavfan/mqtt-db-logger
docker run --name mqtt-db-logger mqtt-db-logger bash




cat <<EOT >> mqtt_db_logger_conf.py
mqtt_brocker="####.cloudapp.net"
topic="#####"
db_srvname="#####"
db_name="#####"
db_username="###"
db_user_pwd="####"
EOT
