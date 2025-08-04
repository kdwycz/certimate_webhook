import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from loguru import logger
from pydantic import BaseModel

from config import AppConfig
from config import app_config as global_config
from sync import SSLSyncer


class WebhookPayload(BaseModel):
    """Webhook请求载荷"""

    name: str


app_config: AppConfig | None = None
ssl_syncer: SSLSyncer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global app_config, ssl_syncer

    # 启动时初始化
    try:
        logger.info("初始化应用配置...")
        app_config = global_config
        ssl_syncer = SSLSyncer(app_config)
        logger.info("初始化完成")

        # 动态注册webhook路由
        webhook_path = f"/{app_config.server.webhook_path}"
        logger.info(f"注册Webhook路径: {webhook_path}")

        # 添加动态路由
        app.add_api_route(
            webhook_path,
            ssl_update_webhook_handler,
            methods=["POST"],
            summary="SSL证书更新webhook",
            description="接收SSL证书更新通知并自动同步到服务器",
        )

        yield
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        raise
    finally:
        # 清理资源
        if ssl_syncer:
            ssl_syncer.cleanup_temp_files()
        logger.info("应用关闭")


# 创建FastAPI应用
app = FastAPI(
    title="SSL证书Webhook",
    description="自动化SSL证书同步服务",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """统一访问日志中间件"""
    start_time = asyncio.get_event_loop().time()
    
    # 获取客户端IP
    client_ip = request.client.host if request.client else "unknown"
    
    # 执行请求
    response = await call_next(request)
    
    # 计算处理时间
    process_time = asyncio.get_event_loop().time() - start_time
    
    # 记录访问日志
    logger.info(
        f'{client_ip} - "{request.method} {request.url.path}" '
        f'{response.status_code} {process_time:.3f}s'
    )
    
    return response


@app.get("/")
async def root():
    raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ssl-certificate-webhook"}


def ssl_update_webhook_handler(
    request: Request, payload: WebhookPayload, background_tasks: BackgroundTasks
):
    """SSL证书更新webhook接口处理器"""
    try:
        # 检查应用配置是否已初始化
        if not app_config or not ssl_syncer:
            raise HTTPException(status_code=503, detail="应用配置未初始化")

        key = payload.name.strip()
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"收到SSL更新请求，key: {key}, 来源IP: {client_ip}")

        if not key:
            raise HTTPException(status_code=400, detail="key不能为空")

        # 查找playbook配置
        playbook_config = app_config.find_playbook_config(key)
        if not playbook_config:
            logger.warning(f"未找到playbook配置: {key}")
            raise HTTPException(status_code=404, detail=f"未找到playbook配置: {key}")

        # 获取对应的服务器组
        server_groups = app_config.get_servers_for_key(key)
        if not server_groups:
            logger.warning(f"key {key} 没有配置服务器组")
            raise HTTPException(
                status_code=404, detail=f"key {key} 没有配置服务器组"
            )

        # 后台异步执行SSL同步
        background_tasks.add_task(
            sync_ssl_certificate_task, key, playbook_config, server_groups
        )

        return {
            "status": "accepted",
            "key": key,
            "server_groups": list(server_groups.keys()),
            "playbook_file": playbook_config.playbook_file,
            "message": "SSL证书同步任务已启动",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理webhook请求失败: {e}")
        raise HTTPException(status_code=500, detail="内部服务器错误") from e


async def sync_ssl_certificate_task(key: str, playbook_config, server_groups):
    """后台SSL证书同步任务"""
    try:
        logger.info(f"开始执行SSL证书同步任务，key: {key}")

        # 检查 ssl_syncer 是否已初始化
        if not ssl_syncer:
            logger.error("SSL同步器未初始化")
            return

        # 在线程池中执行同步操作
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, ssl_syncer.sync_ssl_certificate, key, playbook_config, server_groups
        )

        if success:
            logger.info(f"key {key} SSL证书同步成功")
        else:
            logger.error(f"key {key} SSL证书同步失败")

    except Exception as e:
        logger.error(f"SSL证书同步任务异常: {e}")


class InterceptHandler(logging.Handler):
    """日志拦截器 - 将标准logging重定向到loguru"""
    
    def emit(self, record):
        # 获取对应的loguru级别
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 查找调用者信息
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging():
    """设置统一日志管理 - 拦截所有日志到loguru"""
    # 清除loguru默认处理器  
    logger.remove()
    
    # 添加loguru处理器 - 输出到stdout用于supervisor捕获
    import sys
    logger.add(
        sys.stdout,
        level=global_config.server.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )
    
    # 拦截标准logging到loguru
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    # 禁用uvicorn的默认日志处理器
    for logger_name in ['uvicorn', 'uvicorn.error', 'uvicorn.access', 'fastapi']:
        logging.getLogger(logger_name).handlers = []
        logging.getLogger(logger_name).propagate = True


def main():
    """主函数"""

    # 设置日志
    setup_logging()

    logger.info("启动SSL证书Webhook服务")
    logger.info(f"监听地址: {global_config.server.host}:{global_config.server.port}")
    logger.info("配置文件: config.yml")

    # 启动服务 - 禁用uvicorn内置日志配置
    uvicorn.run(
        "main:app",
        host=global_config.server.host,
        port=global_config.server.port,
        log_config=None,  # 禁用uvicorn默认日志配置
        access_log=False,  # 禁用访问日志，统一由loguru管理
    )


if __name__ == "__main__":
    main()
