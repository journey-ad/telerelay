"""
主程序入口
同时启动 Telegram Bot 和 FastAPI Web 服务
"""
import sys
import uvicorn
from src.config import get_config, reload_config
from src.logger import setup_logger, get_logger
from src.api.app import create_app

# 设置日志
logger = setup_logger()


def main():
    """主函数"""
    try:
        # 加载配置
        config = get_config()
        
        logger.info("=" * 60)
        logger.info("Telegram 消息转发工具启动中...")
        logger.info("=" * 60)
        
        # 重新设置日志级别
        setup_logger(level=config.log_level)
        
        # 创建 FastAPI 应用
        app = create_app()
        
        # 显示访问信息
        logger.info(f"Web 界面地址: http://{config.web_host}:{config.web_port}")
        logger.info(f"API 文档地址: http://{config.web_host}:{config.web_port}/docs")
        logger.info("=" * 60)
        
        # 启动 Web 服务
        uvicorn.run(
            app,
            host=config.web_host,
            port=config.web_port,
            log_level=config.log_level.lower()
        )
        
    except KeyboardInterrupt:
        logger.info("\n收到终止信号，正在关闭...")
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
