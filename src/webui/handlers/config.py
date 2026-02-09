"""
配置处理器
"""
from src.bot_manager import BotManager
from src.config import Config
from src.logger import get_logger
from ..utils import parse_chat_list, format_message

logger = get_logger()


class ConfigHandler:
    """配置处理器"""

    def __init__(self, config: Config, bot_manager: BotManager):
        self.config = config
        self.bot_manager = bot_manager

    def load_config(self) -> dict:
        """
        加载配置到UI

        返回:
            包含所有配置字段的字典
        """
        try:
            return {
                "source_chats": '\n'.join(str(chat) for chat in self.config.source_chats),
                "target_chats": '\n'.join(str(chat) for chat in self.config.target_chats),
                "regex_patterns": '\n'.join(self.config.filter_regex_patterns),
                "keywords": '\n'.join(self.config.filter_keywords),
                "filter_mode": self.config.filter_mode,
                "ignored_user_ids": '\n'.join(str(uid) for uid in self.config.ignored_user_ids),
                "ignored_keywords": '\n'.join(self.config.ignored_keywords),
                "preserve_format": self.config.preserve_format,
                "add_source_info": self.config.add_source_info,
                "delay": self.config.forward_delay
            }

        except Exception as e:
            logger.error(f"加载配置失败: {e}", exc_info=True)
            # 返回默认值
            return {
                "source_chats": "",
                "target_chats": "",
                "regex_patterns": "",
                "keywords": "",
                "filter_mode": "whitelist",
                "ignored_user_ids": "",
                "ignored_keywords": "",
                "preserve_format": True,
                "add_source_info": True,
                "delay": 0.5
            }

    def save_config(
        self,
        source_chats: str,
        target_chats: str,
        regex_patterns: str,
        keywords: str,
        filter_mode: str,
        ignored_user_ids: str,
        ignored_keywords: str,
        preserve_format: bool,
        add_source_info: bool,
        delay: float
    ) -> str:
        """
        保存UI配置

        返回:
            操作结果消息
        """
        try:
            # 解析输入
            source_list = parse_chat_list(source_chats)
            target_list = parse_chat_list(target_chats)
            regex_list = [line.strip() for line in regex_patterns.split('\n') if line.strip()]
            keyword_list = [line.strip() for line in keywords.split('\n') if line.strip()]

            # 解析忽略列表
            ignored_user_id_list = []
            for line in ignored_user_ids.split('\n'):
                line = line.strip()
                if line and line.lstrip('-').isdigit():
                    ignored_user_id_list.append(int(line))

            ignored_keyword_list = [line.strip() for line in ignored_keywords.split('\n') if line.strip()]

            # 基本验证
            if not source_list:
                return format_message("请至少配置一个源群组/频道", "error")

            if not target_list:
                return format_message("请至少配置一个目标群组/频道", "error")

            # 构建配置
            new_config = {
                "source_chats": source_list,
                "target_chats": target_list,
                "filters": {
                    "regex_patterns": regex_list,
                    "keywords": keyword_list,
                    "mode": filter_mode
                },
                "ignore": {
                    "user_ids": ignored_user_id_list,
                    "keywords": ignored_keyword_list
                },
                "forwarding": {
                    "preserve_format": preserve_format,
                    "add_source_info": add_source_info,
                    "delay": float(delay)
                }
            }

            # 保存配置
            self.config.update(new_config)

            logger.info("配置已通过 UI 保存")

            # 智能重启：如果Bot正在运行，自动重启应用新配置
            if self.bot_manager.is_running:
                logger.info("Bot 正在运行，将自动重启以应用新配置")
                success = self.bot_manager.restart()
                if success:
                    return format_message("配置已保存并已重启 Bot 应用新配置！", "success")
                else:
                    return format_message("配置已保存，但重启失败，请手动重启", "success")
            else:
                return format_message("配置已成功保存！下次启动时生效", "success")

        except Exception as e:
            logger.error(f"保存配置失败: {e}", exc_info=True)
            return format_message(f"保存失败: {str(e)}", "error")
