"""
Backup Handler - Configuration import/export
"""
import os
import shutil
import tempfile
import yaml
from src.config import Config
from src.bot_manager import BotManager
from src.logger import get_logger
from src.i18n import t
from ..utils import format_message

logger = get_logger()


class BackupHandler:
    """Configuration backup (import/export) handler"""

    def __init__(self, config: Config, bot_manager: BotManager):
        self.config = config
        self.bot_manager = bot_manager

    def export_config(self):
        """
        Export current config.yaml as a downloadable file.

        Returns:
            File path for download
        """
        try:
            config_path = self.config.config_file
            if not os.path.exists(config_path):
                return None

            tmp_dir = os.path.join(tempfile.gettempdir(), "telerelay-export")
            os.makedirs(tmp_dir, exist_ok=True)
            export_path = os.path.join(tmp_dir, "config.yaml")

            shutil.copy2(config_path, export_path)
            logger.info(t("log.backup.exported"))
            return export_path

        except Exception as e:
            logger.error(t("log.backup.export_failed", error=str(e)))
            return None

    def import_config(self, file):
        """
        Import configuration from uploaded YAML file.

        Args:
            file: Uploaded file object (Gradio file component)

        Returns:
            Status message string
        """
        if file is None:
            return format_message(t("message.backup.no_file"), "error")

        try:
            # Read and validate YAML
            file_path = file.name if hasattr(file, 'name') else file
            with open(file_path, "r", encoding="utf-8") as f:
                new_config = yaml.safe_load(f)

            if not isinstance(new_config, dict):
                return format_message(t("message.backup.invalid_yaml"), "error")

            # Check for required structure
            if "forwarding_rules" not in new_config and "source_chats" not in new_config:
                return format_message(t("message.backup.no_rules_found"), "error")

            # Backup current config
            config_path = self.config.config_file
            if os.path.exists(config_path):
                backup_path = config_path + ".bak"
                shutil.copy2(config_path, backup_path)
                logger.info(t("log.backup.backup_created", path=backup_path))

            # Write new config
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(new_config, f, default_flow_style=False, allow_unicode=True)

            # Reload config
            self.config.load()

            # Restart Bot if running
            if self.bot_manager.is_running:
                self.bot_manager.restart()
                return format_message(t("message.backup.import_success_restarted"), "success")

            return format_message(t("message.backup.import_success"), "success")

        except yaml.YAMLError as e:
            return format_message(t("message.backup.yaml_error", error=str(e)), "error")
        except Exception as e:
            logger.error(t("log.backup.import_failed", error=str(e)), exc_info=True)
            return format_message(t("message.backup.import_failed", error=str(e)), "error")
