"""
Gradio WebUI - Telegram 消息转发工具界面
简洁、直观的配置和控制界面
"""
import gradio as gr
from pathlib import Path
from typing import Tuple, List
from src.bot_manager import get_bot_manager
from src.config import get_config, reload_config
from src.logger import get_logger

logger = get_logger()


# ==================== 工具函数 ====================

def parse_chat_list(text: str) -> List:
    """
    解析聊天列表
    
    参数:
        text: 多行文本，每行一个聊天 ID 或用户名
        
    返回:
        解析后的聊天列表（整数或字符串）
    """
    if not text or not text.strip():
        return []
    
    result = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        # 判断是数字还是用户名
        if line.lstrip('-').isdigit():
            result.append(int(line))
        else:
            result.append(line)
    return result


def format_success(msg: str) -> str:
    """成功消息格式"""
    return f"✅ {msg}"


def format_error(msg: str) -> str:
    """错误消息格式"""
    return f"❌ {msg}"


def format_info(msg: str) -> str:
    """信息消息格式"""
    return f"ℹ️ {msg}"


# ==================== Bot 控制函数 ====================

def start_bot() -> str:
    """启动 Bot"""
    try:
        bot_manager = get_bot_manager()
        
        if bot_manager.is_running:
            return format_info("Bot 已在运行中")
        
        # 验证配置
        config = get_config()
        is_valid, error_msg = config.validate()
        if not is_valid:
            return format_error(f"配置验证失败: {error_msg}")
        
        success = bot_manager.start()
        if success:
            logger.info("Bot 已通过 WebUI 启动")
            return format_success("Bot 已成功启动")
        else:
            return format_error("Bot 启动失败")
            
    except Exception as e:
        logger.error(f"启动 Bot 失败: {e}", exc_info=True)
        return format_error(f"启动失败: {str(e)}")


def stop_bot() -> str:
    """停止 Bot"""
    try:
        bot_manager = get_bot_manager()
        
        if not bot_manager.is_running:
            return format_info("Bot 未在运行")
        
        success = bot_manager.stop()
        if success:
            logger.info("Bot 已通过 WebUI 停止")
            return format_success("Bot 已成功停止")
        else:
            return format_error("Bot 停止失败")
            
    except Exception as e:
        logger.error(f"停止 Bot 失败: {e}", exc_info=True)
        return format_error(f"停止失败: {str(e)}")


def restart_bot() -> str:
    """重启 Bot"""
    try:
        # 重新加载配置
        reload_config()
        
        bot_manager = get_bot_manager()
        success = bot_manager.restart()
        
        if success:
            logger.info("Bot 已通过 WebUI 重启")
            return format_success("Bot 已成功重启")
        else:
            return format_error("Bot 重启失败")
            
    except Exception as e:
        logger.error(f"重启 Bot 失败: {e}", exc_info=True)
        return format_error(f"重启失败: {str(e)}")


def get_status() -> Tuple[str, str, str, str]:
    """
    获取 Bot 状态
    
    返回:
        (状态文本, 已转发数, 已过滤数, 总计数)
    """
    try:
        bot_manager = get_bot_manager()
        status = bot_manager.get_status()
        
        if status['is_running']:
            status_text = "🟢 运行中" if status['is_connected'] else "🟡 连接中..."
        else:
            status_text = "⚫ 已停止"
        
        stats = status.get('stats', {})
        forwarded = str(stats.get('forwarded', 0))
        filtered = str(stats.get('filtered', 0))
        total = str(stats.get('total', 0))
        
        return status_text, forwarded, filtered, total
        
    except Exception as e:
        logger.error(f"获取状态失败: {e}", exc_info=True)
        return "❌ 状态异常", "0", "0", "0"


# ==================== 配置管理函数 ====================

def load_config_to_ui() -> dict:
    """
    加载配置到 UI
    
    返回:
        包含所有配置字段的字典
    """
    try:
        config = get_config()
        
        return {
            "source_chats": '\n'.join(str(chat) for chat in config.source_chats),
            "target_chats": '\n'.join(str(chat) for chat in config.target_chats),
            "regex_patterns": '\n'.join(config.filter_regex_patterns),
            "keywords": '\n'.join(config.filter_keywords),
            "filter_mode": config.filter_mode,
            "ignored_user_ids": '\n'.join(str(uid) for uid in config.ignored_user_ids),
            "ignored_keywords": '\n'.join(config.ignored_keywords),
            "preserve_format": config.preserve_format,
            "add_source_info": config.add_source_info,
            "delay": config.forward_delay
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


# ==================== 配置-组件映射（解耦设计） ====================

class ConfigComponentMapping:
    """
    配置字段和 UI 组件的映射关系
    添加新配置时只需在这里声明一次即可
    """
    def __init__(self):
        # 组件引用字典（在 create_ui 中填充）
        self.components = {}
    
    def set_components(self, **components):
        """设置组件引用"""
        self.components = components
    
    def get_update_list(self, config_dict: dict) -> list:
        """
        根据配置字典生成 Gradio 更新列表
        自动按照组件注册顺序生成
        """
        # 按照组件注册顺序返回值
        return [config_dict.get(key, "") for key in self.components.keys()]
    
    def get_component_list(self) -> list:
        """获取组件列表（用于 outputs）"""
        return list(self.components.values())
    
    @property
    def field_names(self) -> list:
        """获取字段名列表"""
        return list(self.components.keys())


# 全局配置映射实例
_config_mapping = ConfigComponentMapping()





def save_config_from_ui(
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
    保存 UI 配置
    
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
            return format_error("请至少配置一个源群组/频道")
        
        if not target_list:
            return format_error("请至少配置一个目标群组/频道")
        
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
        config = get_config()
        config.update(new_config)
        
        logger.info("配置已通过 UI 保存")
        
        # 智能重启：如果 Bot 正在运行，自动重启应用新配置
        bot_manager = get_bot_manager()
        if bot_manager.is_running:
            logger.info("Bot 正在运行，将自动重启以应用新配置")
            success = bot_manager.restart()
            if success:
                return format_success("配置已保存并已重启 Bot 应用新配置！")
            else:
                return format_success("配置已保存，但重启失败，请手动重启")
        else:
            return format_success("配置已成功保存！下次启动时生效")
        
    except Exception as e:
        logger.error(f"保存配置失败: {e}", exc_info=True)
        return format_error(f"保存失败: {str(e)}")


# ==================== 日志管理 ====================

def get_recent_logs(lines: int = 50) -> str:
    """
    获取最近的日志
    
    参数:
        lines: 返回的日志行数
        
    返回:
        日志文本
    """
    try:
        log_dir = Path("logs")
        
        if not log_dir.exists():
            return "暂无日志"
        
        # 获取最新的日志文件
        log_files = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
        
        if not log_files:
            return "暂无日志"
        
        # 读取最新日志文件的最后 N 行
        log_file = log_files[0]
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
        return ''.join(recent_lines)
        
    except Exception as e:
        logger.error(f"读取日志失败: {e}", exc_info=True)
        return f"读取日志失败: {str(e)}"


# ==================== UI 构建 ====================

def create_ui() -> gr.Blocks:
    """创建 Gradio 界面"""
    
    # 使用柔和主题
    theme = gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="gray",
    )
    
    with gr.Blocks(title="Telegram 消息转发工具", theme=theme) as app:
        
        # 标题
        gr.Markdown("# 📡 Telegram 消息转发工具")
        gr.Markdown("自动监控 Telegram 群组并转发消息到多个目标")
        
        # 事件驱动刷新定时器（快速轮询检查更新标志）
        timer = gr.Timer(value=0.5)  # 0.5秒检查一次
        
        # ===== 控制面板 =====
        with gr.Row():
            start_btn = gr.Button("▶️ 启动", variant="primary", size="sm")
            stop_btn = gr.Button("⏸️ 停止", variant="stop", size="sm")
            restart_btn = gr.Button("🔄 重启", variant="secondary", size="sm")
            refresh_status_btn = gr.Button("🔄 刷新状态", size="sm")
        
        with gr.Row():
            status_text = gr.Textbox(label="状态", value="⚫ 已停止", interactive=False, scale=2)
            forwarded_count = gr.Textbox(label="已转发", value="0", interactive=False, scale=1)
            filtered_count = gr.Textbox(label="已过滤", value="0", interactive=False, scale=1)
            total_count = gr.Textbox(label="总计", value="0", interactive=False, scale=1)
        
        control_message = gr.Textbox(label="操作消息", visible=False)
        
        # ===== 标签页 =====
        with gr.Tabs():
            
            # --- 配置标签 ---
            with gr.Tab("⚙️ 配置"):
                with gr.Group():
                    gr.Markdown("### 📥 源和目标")
                    
                    source_chats = gr.Textbox(
                        label="源群组/频道",
                        placeholder="-100123456789\n@example_channel",
                        lines=4,
                        info="输入要监控的群组 ID 或频道用户名，每行一个"
                    )
                    
                    target_chats = gr.Textbox(
                        label="目标群组/频道",
                        placeholder="-100987654321\n@target_channel\n-1001234567890",
                        lines=4,
                        info="消息将转发到这些位置，每行一个"
                    )
                
                with gr.Group():
                    gr.Markdown("### 🔍 过滤规则")
                    
                    regex_patterns = gr.Textbox(
                        label="正则表达式",
                        placeholder="\\[重要\\].*\n紧急通知.*",
                        lines=3,
                        info="每行一个正则表达式"
                    )
                    
                    keywords = gr.Textbox(
                        label="关键词",
                        placeholder="关键词1\n关键词2",
                        lines=3,
                        info="每行一个关键词"
                    )
                    
                    filter_mode = gr.Radio(
                        choices=["whitelist", "blacklist"],
                        value="whitelist",
                        label="过滤模式",
                        info="whitelist: 仅转发匹配的消息 | blacklist: 转发不匹配的消息"
                    )
                
                with gr.Group():
                    gr.Markdown("### 🚫 忽略列表")
                    gr.Markdown("⚠️ 优先级高于过滤规则，匹配则直接忽略")
                    
                    ignored_user_ids = gr.Textbox(
                        label="忽略的用户 ID",
                        placeholder="123456789\n987654321",
                        lines=3,
                        info="这些用户发送的所有消息将被忽略，每行一个数字 ID（可通过 @userinfobot 获取）"
                    )
                    
                    ignored_keywords = gr.Textbox(
                        label="忽略的关键词",
                        placeholder="广告\n推广\nspam",
                        lines=3,
                        info="包含这些关键词的消息将被忽略，每行一个关键词（不区分大小写）"
                    )
                
                with gr.Group():
                    gr.Markdown("### 📤 转发选项")
                    
                    preserve_format = gr.Checkbox(
                        label="保留原始格式",
                        value=True,
                        info="保留转发标记和原始格式"
                    )
                    
                    add_source_info = gr.Checkbox(
                        label="添加来源信息",
                        value=True,
                        info="在消息前添加来源群组信息"
                    )
                    
                    delay = gr.Slider(
                        minimum=0,
                        maximum=5,
                        value=0.5,
                        step=0.1,
                        label="转发延迟（秒）",
                        info="避免触发 Telegram 限制"
                    )
                
                # ===== 注册配置-组件映射 =====
                # 添加新配置时，只需在这里添加一行即可！
                _config_mapping.set_components(
                    source_chats=source_chats,
                    target_chats=target_chats,
                    regex_patterns=regex_patterns,
                    keywords=keywords,
                    filter_mode=filter_mode,
                    ignored_user_ids=ignored_user_ids,
                    ignored_keywords=ignored_keywords,
                    preserve_format=preserve_format,
                    add_source_info=add_source_info,
                    delay=delay
                )
                
                save_btn = gr.Button("💾 保存配置", variant="primary", size="lg")
                save_message = gr.Textbox(label="保存结果", visible=False)
            
            # --- 日志标签 ---
            with gr.Tab("📋 日志"):
                log_output = gr.Textbox(
                    label="实时日志",
                    lines=25,
                    max_lines=25,
                    interactive=False,
                    show_copy_button=True
                )
                
                with gr.Row():
                    refresh_log_btn = gr.Button("🔄 刷新日志", size="sm")
                    log_lines = gr.Slider(
                        minimum=20,
                        maximum=200,
                        value=50,
                        step=10,
                        label="显示行数",
                        scale=2
                    )
        
        # ===== 事件绑定 =====
        
        # Bot 控制
        start_btn.click(
            fn=start_bot,
            outputs=control_message
        ).then(
            fn=lambda msg: gr.update(visible=bool(msg)),
            inputs=control_message,
            outputs=control_message
        )
        
        stop_btn.click(
            fn=stop_bot,
            outputs=control_message
        ).then(
            fn=lambda msg: gr.update(visible=bool(msg)),
            inputs=control_message,
            outputs=control_message
        )
        
        restart_btn.click(
            fn=restart_bot,
            outputs=control_message
        ).then(
            fn=lambda msg: gr.update(visible=bool(msg)),
            inputs=control_message,
            outputs=control_message
        )
        
        # 配置保存
        save_btn.click(
            fn=save_config_from_ui,
            inputs=[
                source_chats,
                target_chats,
                regex_patterns,
                keywords,
                filter_mode,
                ignored_user_ids,
                ignored_keywords,
                preserve_format,
                add_source_info,
                delay
            ],
            outputs=save_message
        ).then(
            fn=lambda msg: gr.update(visible=bool(msg)),
            inputs=save_message,
            outputs=save_message
        )
        
        # 日志刷新
        refresh_log_btn.click(
            fn=get_recent_logs,
            inputs=log_lines,
            outputs=log_output
        )
        
        # 状态刷新（手动）
        refresh_status_btn.click(
            fn=get_status,
            outputs=[status_text, forwarded_count, filtered_count, total_count]
        )
        
        # 日志刷新（手动）
        refresh_log_btn.click(
            fn=get_recent_logs,
            inputs=log_lines,
            outputs=log_output
        )
        
        # 事件驱动自动刷新 - 只在转发时更新
        def auto_refresh_all(lines):
            """检查是否有更新事件，有则刷新状态和日志"""
            # 检查是否需要更新
            manager = get_bot_manager()
            if manager and manager.check_and_clear_ui_update():
                status = get_status()
                logs = get_recent_logs(lines)
                return status + (logs,)
            # 无更新则返回 gr.update() 保持不变
            return [gr.update()] * 5
        
        timer.tick(
            fn=auto_refresh_all,
            inputs=log_lines,
            outputs=[status_text, forwarded_count, filtered_count, total_count, log_output]
        )
        
        # ===== 页面加载时初始化 =====
        
        # 加载时自动加载配置
        app.load(
            fn=lambda: _config_mapping.get_update_list(load_config_to_ui()),
            outputs=_config_mapping.get_component_list()
        )
        
        # 加载时获取一次状态
        app.load(
            fn=get_status,
            outputs=[status_text, forwarded_count, filtered_count, total_count]
        )
        
        # 加载时自动刷新日志
        app.load(
            fn=get_recent_logs,
            inputs=log_lines,
            outputs=log_output
        )
    
    return app
