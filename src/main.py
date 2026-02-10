"""
Telegram Message Forwarder - Main Entry Point
Provides WebUI interface using Gradio
"""
import sys
from pathlib import Path
from src.webui import create_ui
from src.config import create_config
from src.bot_manager import BotManager
from src.auth_manager import AuthManager
from src.logger import setup_logger, get_logger, add_ui_update_handler
from src.i18n import t, set_language

# Setup logger
logger = setup_logger()


def main():
    """Start the application"""
    try:
        # Create configuration
        config = create_config()

        # Set language
        set_language(config.language)

        logger.info("=" * 60)
        logger.info(t("log.main.startup"))
        logger.info("=" * 60)

        # Reset log level
        setup_logger(level=config.log_level)

        # Create AuthManager (only needed in User mode)
        auth_manager = None
        if config.session_type == "user":
            auth_manager = AuthManager(input_timeout=300)
            logger.info(t("log.main.auth_manager_created"))

        # Create Bot manager
        bot_manager = BotManager(config, auth_manager)

        # Automatically trigger UI update when logging
        add_ui_update_handler(bot_manager)

        # Auto-login if session cache exists
        session_file = Path("sessions/telegram_session.session")
        if session_file.exists():
            logger.info(t("log.main.session_detected"))
            bot_manager.start()

        # Create Gradio interface
        app = create_ui(config, bot_manager, auth_manager)

        # Display access information
        logger.info(t("log.main.web_address", host=config.web_host, port=config.web_port))
        logger.info("=" * 60)

        # Prepare authentication configuration
        auth = None
        if config.web_auth_username and config.web_auth_password:
            auth = (config.web_auth_username, config.web_auth_password)
            logger.info(t("log.main.auth_enabled"))
        else:
            logger.warning(t("log.main.auth_warning"))

        # Start Gradio service
        app.launch(
            server_name=config.web_host,
            server_port=config.web_port,
            share=False,
            show_error=True,
            quiet=False,
            auth=auth
        )

    except KeyboardInterrupt:
        logger.info(t("log.main.shutdown"))
    except Exception as e:
        logger.error(t("log.main.error", error=str(e)), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
