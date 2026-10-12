# Pinggu Agent 迁移说明

## 1. 当前目录

- 原项目：E:\pinggu agent
- 本次迁移副本：E:\wjh agent
- 正确前端目录：frontend-discovery
- 旧前端目录：frontend，已从原项目和迁移副本中删除。
- 生产 Compose：docker-compose.prod.yml
- 生产前端构建上下文：./frontend-discovery
- 后端镜像构建文件：Dockerfile.backend

本次复制保留了项目源码、Docker 配置、依赖目录、构建产物、模型和本地数据文件，因此目录体积较大。迁移时应以 frontend-discovery 为准，不要重新创建或引用已删除的 frontend。

## 2. 本地前端开发

进入前端目录：

    cd "E:\wjh agent\frontend-discovery"
    npm run dev

构建生产前端：

    cd "E:\wjh agent\frontend-discovery"
    npm run build

如果目标电脑没有可用的 node_modules，先执行：

    npm install

## 3. 服务器信息

当前生产服务器：

- 腾讯云南京
- Ubuntu Server 22.04 LTS
- 4 核 CPU、16 GB 内存、220 GB SSD
- 公网 IP：119.45.61.81
- 项目目录：/opt/pinggu
- 当前访问地址：http://119.45.61.81/
- 健康检查：http://119.45.61.81/health

服务器使用 Docker Compose 运行 PostgreSQL、Milvus、MinIO、etcd、后端和 Nginx 前端。数据库、Milvus、MinIO 和 etcd 只应通过 Docker 内网访问，不要把这些端口开放到公网。

## 4. 生产部署命令

登录服务器后：

    cd /opt/pinggu
    sudo docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build

查看容器状态：

    cd /opt/pinggu
    sudo docker compose --env-file .env.production -f docker-compose.prod.yml ps

查看全部日志：

    sudo docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=200

查看后端日志：

    sudo docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=200 backend

重启服务：

    sudo docker compose --env-file .env.production -f docker-compose.prod.yml restart

更新代码后重新构建：

    cd /opt/pinggu
    sudo docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build

检查接口：

    curl http://127.0.0.1/health

浏览器访问：

    http://119.45.61.81/

## 5. 配置和安全

- .env.production 含数据库密码、模型/API 配置、JWT 密钥等敏感信息，不要提交到公开仓库、聊天记录或截图中。
- 迁移到新服务器时，应单独填写新的 .env.production，并检查 DB_*、MINIO_*、JWT_*、模型和 DeepSeek 配置。
- 曾经在聊天或终端中暴露过的服务器密码、API Key 和密钥，正式交付前应轮换。
- 腾讯云安全组至少放行 TCP 22（SSH）和 TCP 80（网站）；数据库、Milvus、MinIO、etcd 端口不要放行公网。
- 当前服务器使用本地 CPU 模型，配置为 4 核 16 GB；多人并发较高时需关注内存、CPU 和响应时间。

## 6. 迁移检查清单

1. 确认服务器 Ubuntu、Docker 和 Docker Compose 已安装。
2. 将项目文件上传到服务器的 /opt/pinggu。
3. 在服务器创建并核对 .env.production，不要覆盖成示例文件。
4. 执行生产 Compose 启动命令。
5. 用 docker compose ps 确认所有服务为运行或健康状态。
6. 访问 /health 和首页，完成登录、问答、文件上传等基本验收。
7. 配置定期备份 Docker volumes：postgres_data、milvus_data、minio_data、app_data。
8. 后续有域名时，再配置 DNS、备案和 HTTPS；当前可继续使用公网 IP 访问。

## 7. 交接提示

下一次迁移或维护会话应先阅读本文件和 docker-compose.prod.yml。生产前端目录是 frontend-discovery，旧的 frontend 已删除。若修改前端构建路径、后端端口或环境变量，必须同步检查 Dockerfile、Nginx 配置和生产 Compose。
