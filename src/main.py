"""
Telegram 消息转发工具 - 主入口
使用 Gradio 提供 WebUI 界面
"""
import sys
from src.webui import create_ui
from src.config import get_config
from src.logger import setup_logger, get_logger

# 设置日志
logger = setup_logger()


def main():
    """启动应用"""
    try:
        # 加载配置
        config = get_config()
        
        logger.info("=" * 60)
        logger.info("Telegram 消息转发工具启动中...")
        logger.info("=" * 60)
        
        # 重新设置日志级别
        setup_logger(level=config.log_level)
        
        # 创建 Gradio 界面
        app = create_ui()
        
        # 显示访问信息
        logger.info(f"Web 界面地址: http://{config.web_host}:{config.web_port}")
        logger.info("=" * 60)
        
        # 准备认证配置
        auth = None
        if config.web_auth_username and config.web_auth_password:
            auth = (config.web_auth_username, config.web_auth_password)
            logger.info("✓ HTTP Basic Auth 已启用")
        else:
            logger.warning("⚠ HTTP Basic Auth 未启用，建议在生产环境配置认证")
        
        # 启动 Gradio 服务
        app.launch(
            server_name=config.web_host,
            server_port=config.web_port,
            share=False,
            show_error=True,
            quiet=False,
            auth=auth
        )
        
    except KeyboardInterrupt:
        logger.info("\n收到终止信号，正在关闭...")
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
