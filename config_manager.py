import json
import os
import logging
import shutil
from datetime import datetime, timedelta
import uuid
from utils import resource_path

CONFIG_FILE = "config.json"

# 单个角色的默认配置模板
DEFAULT_CHARACTER_CONFIG = {
    "id": "",
    "name": "新角色",
    "avatar": "character.png",
    
    # 角色设定
    "persona": "你是一个严厉但关心的私人健康助理，说话喜欢带点冷幽默。",
    "user_identity": "我是一个需要健康提醒的普通用户。",
    "user_name": "用户",  # 用户名称，默认为"用户"
    
    # 喝水相关
    "daily_target_cups": 7.5,
    "cups_drunk_today": 0.0,
    "last_reset_date": datetime.now().strftime("%Y-%m-%d"),
    "last_daily_briefing_date": "",
    
    # 工作时间（兼容旧版本）
    "work_start_time": "09:00",
    "work_end_time": "18:00",
    
    # 每周工作时间表
    "weekly_schedule": {
        "Monday": {"enabled": True, "start": "09:00", "end": "18:00"},
        "Tuesday": {"enabled": True, "start": "09:00", "end": "18:00"},
        "Wednesday": {"enabled": True, "start": "09:00", "end": "18:00"},
        "Thursday": {"enabled": True, "start": "09:00", "end": "18:00"},
        "Friday": {"enabled": True, "start": "09:00", "end": "18:00"},
        "Saturday": {"enabled": False, "start": "10:00", "end": "17:00"},
        "Sunday": {"enabled": False, "start": "10:00", "end": "17:00"}
    },
    
    # 提醒设置
    "enable_random_chat": False,
    "random_chat_interval": 60,
    "reminders": {
        "water": {
            "enabled": True,
            "type": "interval",
            "interval": 60,
            "last_triggered": None
        },
        "meal": {
            "enabled": True,
            "type": "fixed",
            "times": ["08:00", "12:00", "18:30"],
            "last_triggered": None
        },
        "sitting": {
            "enabled": True,
            "type": "interval",
            "interval": 45,
            "last_triggered": None
        },
        "relax": {
            "enabled": True,
            "type": "interval",
            "interval": 90,
            "last_triggered": None
        },
        "custom": []
    },
    
    # 聊天记录
    "chat_history": [],
    
    # Lorebook (背景知识)
    "lorebook": [],
    
    # 纪念日
    "anniversaries": [],
    
    # 健康管理
    "health": {
        "period_tracker": {
            "enabled": False,
            "cycle_length": 28,
            "period_length": 5,
            "last_start_date": None,
            "history": []
        },
        "medication_reminders": []
    },
    
    # 触摸互动区域
    "touch_areas": {
        "enabled": True,
        "areas": []
    },
    
    # 表情系统
    "expressions": {
        "default": "character.png",
        "mappings": {},
        "restore_delay": 10
    },
    
    # 外观自定义
    "appearance": {
        "bubble": {
            "background_color": "#FFFFFF",
            "border_color": "#646464",
            "text_color": "#323232",
            "corner_radius": 14,
            "padding_x": 30,
            "padding_y": 28,
            "font_size": 14,
            "border_width": 1,
            "font_type": "system",  # "system"（系统字体）或 "custom"（自定义字体文件）
            "font_name": "Microsoft YaHei UI",  # 系统字体名称
            "font_file": ""  # 自定义字体文件路径
        },
        "input_box": {
            "background_color": "#FFFFFF",
            "border_color": "#E5E5E5",
            "text_color": "#333333",
            "button_color": "#7EA0B7",
            "button_hover_color": "#6C8EA4",
            "corner_radius": 30,
            "font_size": 13
        }
    }
}

# 全局默认配置
DEFAULT_GLOBAL_CONFIG = {
    "api_base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-3.5-turbo",
    "max_history_messages": 10,  # 发送给AI的最大历史消息数
    "weather_city": "",
    "weather_api_key": "",
    "current_character": None,
    "characters": {}
}

class ConfigManager:
    def __init__(self):
        self.config = self.load_config()
        self.check_daily_reset()

    def load_config(self):
        """加载配置文件"""
        # 尝试加载外部配置文件
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                    # 检查是否是新的多角色格式
                    if "characters" in config and "current_character" in config:
                        # 新格式，直接返回
                        return config
                    else:
                        # 旧格式，需要迁移
                        logging.info("检测到旧版配置格式，自动迁移到多角色格式")
                        return self._migrate_old_config(config)
            except Exception as e:
                logging.error(f"加载配置失败: {e}")
        
        # 配置文件不存在，创建默认配置
        config = DEFAULT_GLOBAL_CONFIG.copy()
        
        # 尝试加载打包的默认配置
        internal_config_path = resource_path("default_config.json")
        if os.path.exists(internal_config_path):
            try:
                with open(internal_config_path, 'r', encoding='utf-8') as f:
                    internal_config = json.load(f)
                    if "persona" in internal_config:
                        # 打包配置包含角色设定，作为第一个角色
                        char_config = DEFAULT_CHARACTER_CONFIG.copy()
                        char_config["id"] = "char_default"
                        char_config["name"] = internal_config.get("name", "默认角色")
                        char_config["persona"] = internal_config.get("persona", "")
                        char_config["lorebook"] = internal_config.get("lorebook", [])
                        config["characters"]["char_default"] = char_config
                        config["current_character"] = "char_default"
            except Exception as e:
                logging.error(f"加载内置配置失败: {e}")
        
        # 如果没有任何角色，创建一个默认角色
        if not config["characters"]:
            char_id = "char_" + str(uuid.uuid4())[:8]
            char_config = DEFAULT_CHARACTER_CONFIG.copy()
            char_config["id"] = char_id
            char_config["name"] = "默认助手"
            config["characters"][char_id] = char_config
            config["current_character"] = char_id
        
        self.save_config(config)
        return config
    
    def _migrate_old_config(self, old_config):
        """迁移旧版单角色配置到新版多角色格式"""
        new_config = DEFAULT_GLOBAL_CONFIG.copy()
        
        # 全局设置
        new_config["api_base_url"] = old_config.get("api_base_url", "https://api.openai.com/v1")
        new_config["api_key"] = old_config.get("api_key", "")
        new_config["model"] = old_config.get("model", "gpt-3.5-turbo")
        
        # 创建第一个角色（从旧配置迁移）
        char_id = "char_default"
        char_config = DEFAULT_CHARACTER_CONFIG.copy()
        char_config["id"] = char_id
        char_config["name"] = "默认角色"
        
        # 迁移所有角色相关配置
        character_keys = [
            "persona", "user_identity", "daily_target_cups", "cups_drunk_today",
            "last_reset_date", "work_start_time", "work_end_time", "weekly_schedule",
            "enable_random_chat", "random_chat_interval", "reminders", "chat_history",
            "lorebook", "anniversaries", "health", "touch_areas", "expressions", "appearance"
        ]
        
        for key in character_keys:
            if key in old_config:
                char_config[key] = old_config[key]
        
        new_config["characters"][char_id] = char_config
        new_config["current_character"] = char_id
        
        # 保存迁移后的配置
        self.save_config(new_config)
        logging.info("配置迁移完成")
        
        return new_config

    def save_config(self, new_config=None):
        """保存配置文件"""
        if new_config:
            self.config = new_config
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)

    def get_current_character_id(self):
        """获取当前角色ID"""
        return self.config.get("current_character")
    
    def get_current_character(self):
        """获取当前角色的完整配置"""
        char_id = self.get_current_character_id()
        if char_id and char_id in self.config.get("characters", {}):
            return self.config["characters"][char_id]
        # 如果没有当前角色，返回第一个角色
        characters = self.config.get("characters", {})
        if characters:
            first_char_id = list(characters.keys())[0]
            self.config["current_character"] = first_char_id
            self.save_config()
            return characters[first_char_id]
        return None
    
    def get_all_characters(self):
        """获取所有角色的列表 (仅基本信息)"""
        characters = []
        for char_id, char_config in self.config.get("characters", {}).items():
            characters.append({
                "id": char_id,
                "name": char_config.get("name", "未命名"),
                "avatar": char_config.get("avatar", "character.png")
            })
        return characters
    
    def switch_character(self, char_id):
        """切换到指定角色"""
        if char_id in self.config.get("characters", {}):
            self.config["current_character"] = char_id
            self.save_config()
            self.check_daily_reset()  # 切换角色后检查日期重置
            return True
        return False
    
    def create_character(self, name, persona="", user_identity="", avatar="character.png"):
        """创建新角色"""
        from utils import name_to_pinyin
        
        # 使用拼音生成角色ID
        pinyin = name_to_pinyin(name)
        char_id = f"char_{pinyin}"
        
        # 如果ID已存在，添加数字后缀
        if char_id in self.config.get("characters", {}):
            counter = 1
            while f"{char_id}{counter}" in self.config.get("characters", {}):
                counter += 1
            char_id = f"{char_id}{counter}"
        
        # 创建角色专属目录
        char_dir = os.path.join("characters", char_id)
        os.makedirs(char_dir, exist_ok=True)
        logging.info(f"Created character directory: {char_dir}")
        
        # 如果提供了avatar且不是默认值，复制到角色目录
        final_avatar = avatar
        if avatar != "character.png" and os.path.exists(avatar):
            try:
                _, ext = os.path.splitext(avatar)
                avatar_dest = os.path.join(char_dir, f"character{ext}")
                shutil.copy2(avatar, avatar_dest)
                final_avatar = avatar_dest
                logging.info(f"Copied avatar: {avatar} -> {avatar_dest}")
            except Exception as e:
                logging.error(f"Failed to copy avatar: {e}")
                final_avatar = avatar
        else:
            # 使用相对路径指向角色目录中的 character.png
            final_avatar = os.path.join(char_dir, "character.png")
        
        char_config = DEFAULT_CHARACTER_CONFIG.copy()
        char_config["id"] = char_id
        char_config["name"] = name
        char_config["persona"] = persona if persona else DEFAULT_CHARACTER_CONFIG["persona"]
        char_config["user_identity"] = user_identity if user_identity else DEFAULT_CHARACTER_CONFIG["user_identity"]
        char_config["avatar"] = final_avatar
        
        # 同时设置 expressions.default 为相同的立绘路径
        if "expressions" not in char_config:
            char_config["expressions"] = {
                "default": final_avatar,
                "mappings": {},
                "restore_delay": 10
            }
        else:
            char_config["expressions"]["default"] = final_avatar
        
        self.config["characters"][char_id] = char_config
        self.save_config()
        return char_id
    
    def delete_character(self, char_id):
        """删除角色"""
        # 不能删除当前角色或唯一角色
        if len(self.config.get("characters", {})) <= 1:
            return False, "至少需要保留一个角色"
        
        if char_id == self.get_current_character_id():
            return False, "不能删除当前使用的角色，请先切换到其他角色"
        
        if char_id in self.config.get("characters", {}):
            # 删除角色配置
            del self.config["characters"][char_id]
            self.save_config()
            
            # 删除角色资源目录
            char_dir = os.path.join("characters", char_id)
            if os.path.exists(char_dir):
                try:
                    shutil.rmtree(char_dir)
                    logging.info(f"Deleted character directory: {char_dir}")
                except Exception as e:
                    logging.error(f"Failed to delete character directory: {e}")
            
            return True, "删除成功"
        
        return False, "角色不存在"
    
    def update_character_config(self, char_id, key, value):
        """更新指定角色的配置项"""
        if char_id in self.config.get("characters", {}):
            self.config["characters"][char_id][key] = value
            self.save_config()
            return True
        return False

    def get(self, key, default=None):
        """获取配置项（优先从当前角色，其次从全局）"""
        # 全局配置项
        global_keys = ["api_base_url", "api_key", "model", "max_history_messages", "weather_city", "weather_api_key", "current_character", "characters"]
        
        if key in global_keys:
            return self.config.get(key, default)
        
        # 角色配置项
        current_char = self.get_current_character()
        if current_char:
            return current_char.get(key, default)
        
        return default

    def set(self, key, value):
        """设置配置项（自动判断是全局还是角色配置）"""
        global_keys = ["api_base_url", "api_key", "model", "max_history_messages", "weather_city", "weather_api_key", "current_character"]
        
        if key in global_keys:
            self.config[key] = value
        else:
            # 设置当前角色的配置
            char_id = self.get_current_character_id()
            if char_id and char_id in self.config.get("characters", {}):
                self.config["characters"][char_id][key] = value
        
        self.save_config()

    def check_daily_reset(self):
        """检查是否是新的一天，重置喝水计数和提醒时间"""
        current_char = self.get_current_character()
        if not current_char:
            return
        
        today = datetime.now().strftime("%Y-%m-%d")
        if current_char.get("last_reset_date") != today:
            char_id = self.get_current_character_id()
            self.config["characters"][char_id]["cups_drunk_today"] = 0.0
            self.config["characters"][char_id]["last_reset_date"] = today
            
            # 重置所有提醒的触发时间
            if "reminders" in self.config["characters"][char_id]:
                for reminder_type in self.config["characters"][char_id]["reminders"]:
                    if isinstance(self.config["characters"][char_id]["reminders"][reminder_type], dict):
                        self.config["characters"][char_id]["reminders"][reminder_type]["last_triggered"] = None
            
            self.save_config()
    
    def get_today_schedule(self):
        """获取今天的工作时间"""
        day_name = datetime.now().strftime("%A")
        weekly_schedule = self.get("weekly_schedule")
        
        if weekly_schedule and day_name in weekly_schedule:
            schedule = weekly_schedule[day_name]
            if schedule.get("enabled", False):
                return schedule.get("start"), schedule.get("end")
        
        return None, None
    
    def is_work_day(self):
        """判断今天是否是工作日"""
        day_name = datetime.now().strftime("%A")
        weekly_schedule = self.get("weekly_schedule")
        
        if weekly_schedule and day_name in weekly_schedule:
            return weekly_schedule[day_name].get("enabled", False)
        
        return True
    
    def get_reminder_config(self, reminder_type):
        """获取特定提醒类型的配置"""
        reminders = self.get("reminders")
        if reminders and reminder_type in reminders:
            return reminders[reminder_type]
        return None
    
    def update_reminder_last_triggered(self, reminder_type):
        """更新提醒的最后触发时间"""
        char_id = self.get_current_character_id()
        if not char_id or char_id not in self.config.get("characters", {}):
            return
        
        char_config = self.config["characters"][char_id]
        if "reminders" not in char_config:
            return
        
        if reminder_type in char_config["reminders"]:
            if isinstance(char_config["reminders"][reminder_type], dict):
                char_config["reminders"][reminder_type]["last_triggered"] = datetime.now().isoformat()
                self.save_config()

    def add_chat_history(self, role, content):
        """添加聊天记录，保留最近20条"""
        char_id = self.get_current_character_id()
        if not char_id or char_id not in self.config.get("characters", {}):
            return
        
        history = self.config["characters"][char_id].get("chat_history", [])
        history.append({"role": role, "content": content})
        if len(history) > 20:
            history = history[-20:]
        self.config["characters"][char_id]["chat_history"] = history
        self.save_config()
        
    def get_chat_history(self):
        return self.get("chat_history") or []
    
    def add_anniversary(self, title, date_str, anniversary_type, notes=""):
        """添加纪念日"""
        char_id = self.get_current_character_id()
        if not char_id or char_id not in self.config.get("characters", {}):
            return
        
        anniversaries = self.config["characters"][char_id].get("anniversaries", [])
        anniversaries.append({
            "id": str(datetime.now().timestamp()),
            "title": title,
            "date": date_str,
            "type": anniversary_type,
            "notes": notes
        })
        self.config["characters"][char_id]["anniversaries"] = anniversaries
        self.save_config()
    
    def remove_anniversary(self, anniversary_id):
        """删除纪念日"""
        char_id = self.get_current_character_id()
        if not char_id or char_id not in self.config.get("characters", {}):
            return
        
        anniversaries = self.config["characters"][char_id].get("anniversaries", [])
        anniversaries = [a for a in anniversaries if a.get("id") != anniversary_id]
        self.config["characters"][char_id]["anniversaries"] = anniversaries
        self.save_config()
    
    def get_today_anniversaries(self):
        """获取今天的纪念日列表"""
        today = datetime.now().strftime("%m-%d")
        anniversaries = self.get("anniversaries") or []
        today_anniversaries = [a for a in anniversaries if a.get("date") == today]
        return today_anniversaries
    
    # ============ 健康管理 ============
    
    def record_period_start(self, date_str=None):
        """记录生理期开始"""
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        char_id = self.get_current_character_id()
        if not char_id or char_id not in self.config.get("characters", {}):
            return
        
        health = self.config["characters"][char_id].get("health", {})
        if "period_tracker" not in health:
            health["period_tracker"] = {
                "enabled": False,
                "cycle_length": 28,
                "period_length": 5,
                "last_start_date": None,
                "history": []
            }
        
        period_tracker = health["period_tracker"]
        period_tracker["last_start_date"] = date_str
        period_tracker["enabled"] = True
        
        if "history" not in period_tracker:
            period_tracker["history"] = []
        period_tracker["history"].append({"date": date_str})
        
        if len(period_tracker["history"]) > 12:
            period_tracker["history"] = period_tracker["history"][-12:]
        
        self.config["characters"][char_id]["health"] = health
        self.save_config()
    
    def get_period_status(self):
        """获取生理期状态"""
        health = self.get("health") or {}
        period_tracker = health.get("period_tracker", {})
        
        if not period_tracker.get("enabled") or not period_tracker.get("last_start_date"):
            return {"status": "disabled"}
        
        try:
            last_start = datetime.strptime(period_tracker["last_start_date"], "%Y-%m-%d")
            cycle_length = period_tracker.get("cycle_length", 28)
            period_length = period_tracker.get("period_length", 5)
            
            today = datetime.now()
            days_since_last = (today - last_start).days
            
            next_date = last_start + timedelta(days=cycle_length)
            days_until = (next_date - today).days
            
            if days_since_last < period_length:
                return {
                    "status": "in_period",
                    "period_day": days_since_last + 1,
                    "days_until": days_until,
                    "next_date": next_date.strftime("%Y-%m-%d")
                }
            elif days_until <= 5 and days_until > 0:
                return {
                    "status": "approaching",
                    "days_until": days_until,
                    "next_date": next_date.strftime("%Y-%m-%d")
                }
            else:
                return {
                    "status": "normal",
                    "days_until": days_until,
                    "next_date": next_date.strftime("%Y-%m-%d")
                }
        except Exception as e:
            logging.error(f"Error calculating period status: {e}")
            return {"status": "error"}
    
    def add_medication_reminder(self, name, times, notes=""):
        """添加吃药提醒"""
        char_id = self.get_current_character_id()
        if not char_id or char_id not in self.config.get("characters", {}):
            return
        
        health = self.config["characters"][char_id].get("health", {})
        if "medication_reminders" not in health:
            health["medication_reminders"] = []
        
        medication = {
            "id": str(datetime.now().timestamp()),
            "name": name,
            "times": times,
            "notes": notes,
            "enabled": True
        }
        
        health["medication_reminders"].append(medication)
        self.config["characters"][char_id]["health"] = health
        self.save_config()
    
    def remove_medication_reminder(self, med_id):
        """删除吃药提醒"""
        char_id = self.get_current_character_id()
        if not char_id or char_id not in self.config.get("characters", {}):
            return
        
        health = self.config["characters"][char_id].get("health", {})
        if "medication_reminders" in health:
            health["medication_reminders"] = [
                m for m in health["medication_reminders"] 
                if m.get("id") != med_id
            ]
            self.config["characters"][char_id]["health"] = health
            self.save_config()
    
    def get_medication_reminders(self):
        """获取所有吃药提醒"""
        health = self.get("health") or {}
        return health.get("medication_reminders", [])

    def export_character(self, char_id, export_path):
        """导出角色为ZIP包
        
        Args:
            char_id: 角色ID
            export_path: 导出文件路径（不含.zip后缀）
        
        Returns:
            (success: bool, message: str)
        """
        import zipfile
        import tempfile
        
        # 检查角色是否存在
        if char_id not in self.config.get("characters", {}):
            return False, "角色不存在"
        
        char_config = self.config["characters"][char_id]
        
        try:
            # 创建临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = os.path.join(temp_dir, "character")
                os.makedirs(temp_path, exist_ok=True)
                
                # 1. 保存角色配置
                config_file = os.path.join(temp_path, "character.json")
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(char_config, f, indent=4, ensure_ascii=False)
                
                # 2. 收集资源文件
                resources = []
                
                # 立绘文件
                avatar = char_config.get("avatar", "character.png")
                if os.path.exists(avatar):
                    resources.append(("avatar", avatar))
                
                # 表情文件
                expressions = char_config.get("expressions", {})
                if isinstance(expressions, dict):
                    # 默认表情
                    default_expr = expressions.get("default", "")
                    if default_expr and os.path.exists(default_expr):
                        resources.append(("expressions/default", default_expr))
                    
                    # 表情映射
                    mappings = expressions.get("mappings", {})
                    for expr_name, expr_path in mappings.items():
                        if expr_path and os.path.exists(expr_path):
                            resources.append((f"expressions/{expr_name}", expr_path))
                
                # 字体文件
                appearance = char_config.get("appearance", {})
                if isinstance(appearance, dict):
                    bubble_style = appearance.get("bubble", {})
                    font_type = bubble_style.get("font_type", "custom")
                    font_file = bubble_style.get("font_file", "")
                    
                    # 如果使用自定义字体文件且文件存在，打包它
                    if font_type == "custom" and font_file and os.path.exists(font_file):
                        # 保留原文件名和扩展名
                        font_filename = os.path.basename(font_file)
                        resources.append((f"fonts/{font_filename}", font_file))
                
                # 3. 复制资源文件到临时目录
                for relative_path, source_path in resources:
                    dest_path = os.path.join(temp_path, relative_path)
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(source_path, dest_path)
                
                # 4. 创建ZIP文件
                zip_path = export_path if export_path.endswith('.zip') else f"{export_path}.zip"
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # 添加所有文件到ZIP
                    for root, dirs, files in os.walk(temp_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, temp_path)
                            zipf.write(file_path, arcname)
                
                char_name = char_config.get("name", "未知")
                return True, f"角色 '{char_name}' 导出成功！\n文件: {zip_path}"
                
        except Exception as e:
            logging.error(f"Export character failed: {e}")
            return False, f"导出失败: {str(e)}"
    
    def import_character(self, zip_path):
        """从ZIP包导入角色
        
        Args:
            zip_path: ZIP文件路径
        
        Returns:
            (success: bool, message: str, char_id: str)
        """
        import zipfile
        import tempfile
        
        if not os.path.exists(zip_path):
            return False, "文件不存在", None
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # 1. 解压ZIP文件
                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                # 2. 读取角色配置
                config_file = os.path.join(temp_dir, "character.json")
                if not os.path.exists(config_file):
                    return False, "无效的角色包：缺少配置文件", None
                
                with open(config_file, 'r', encoding='utf-8') as f:
                    char_config = json.load(f)
                
                # 3. 验证配置
                if not isinstance(char_config, dict):
                    return False, "无效的配置格式", None
                
                # 4. 生成新的角色ID（避免冲突）
                new_char_id = "char_" + str(uuid.uuid4())[:8]
                char_config["id"] = new_char_id
                
                # 5. 导入资源文件
                # 创建角色专属目录
                char_dir = os.path.join("characters", new_char_id)
                os.makedirs(char_dir, exist_ok=True)
                
                # 导入立绘
                avatar_src = os.path.join(temp_dir, "avatar")
                if os.path.exists(avatar_src):
                    # 保留原文件扩展名
                    _, ext = os.path.splitext(avatar_src)
                    avatar_dest = os.path.join(char_dir, f"character{ext}")
                    shutil.copy2(avatar_src, avatar_dest)
                    char_config["avatar"] = avatar_dest
                
                # 导入字体文件
                fonts_dir = os.path.join(temp_dir, "fonts")
                if os.path.exists(fonts_dir):
                    # 创建字体目录
                    char_fonts_dir = os.path.join(char_dir, "fonts")
                    os.makedirs(char_fonts_dir, exist_ok=True)
                    
                    appearance = char_config.get("appearance", {})
                    if isinstance(appearance, dict):
                        bubble_style = appearance.get("bubble", {})
                        font_file = bubble_style.get("font_file", "")
                        
                        # 如果配置中有字体文件路径
                        if font_file:
                            font_filename = os.path.basename(font_file)
                            font_src = os.path.join(fonts_dir, font_filename)
                            
                            if os.path.exists(font_src):
                                font_dest = os.path.join(char_fonts_dir, font_filename)
                                shutil.copy2(font_src, font_dest)
                                # 更新配置中的字体路径
                                bubble_style["font_file"] = font_dest
                                appearance["bubble"] = bubble_style
                                char_config["appearance"] = appearance
                
                # 导入表情
                expressions_dir = os.path.join(temp_dir, "expressions")
                if os.path.exists(expressions_dir):
                    # 创建表情目录
                    char_expr_dir = os.path.join(char_dir, "expressions")
                    os.makedirs(char_expr_dir, exist_ok=True)
                    
                    expressions = char_config.get("expressions", {})
                    if isinstance(expressions, dict):
                        # 更新默认表情路径
                        if "default" in expressions:
                            default_src = os.path.join(expressions_dir, "default")
                            if os.path.exists(default_src):
                                _, ext = os.path.splitext(default_src)
                                default_dest = os.path.join(char_expr_dir, f"default{ext}")
                                shutil.copy2(default_src, default_dest)
                                expressions["default"] = default_dest
                        
                        # 更新表情映射路径
                        mappings = expressions.get("mappings", {})
                        new_mappings = {}
                        for expr_name in mappings.keys():
                            expr_src = os.path.join(expressions_dir, expr_name)
                            if os.path.exists(expr_src):
                                _, ext = os.path.splitext(expr_src)
                                expr_dest = os.path.join(char_expr_dir, f"{expr_name}{ext}")
                                shutil.copy2(expr_src, expr_dest)
                                new_mappings[expr_name] = expr_dest
                            else:
                                # 如果文件不存在，保留原路径（可能是共享的表情）
                                new_mappings[expr_name] = mappings[expr_name]
                        
                        if new_mappings:
                            expressions["mappings"] = new_mappings
                        char_config["expressions"] = expressions
                
                # 6. 清理敏感数据（导入时重置）
                char_config["cups_drunk_today"] = 0.0
                char_config["last_reset_date"] = datetime.now().strftime("%Y-%m-%d")
                
                # 清空聊天历史（可选，用户可能想保留）
                # char_config["chat_history"] = []
                
                # 重置提醒触发时间
                if "reminders" in char_config:
                    for reminder_type in char_config["reminders"]:
                        if isinstance(char_config["reminders"][reminder_type], dict):
                            char_config["reminders"][reminder_type]["last_triggered"] = None
                
                # 7. 添加角色到配置
                self.config["characters"][new_char_id] = char_config
                self.save_config()
                
                char_name = char_config.get("name", "未知")
                return True, f"角色 '{char_name}' 导入成功！", new_char_id
                
        except Exception as e:
            logging.error(f"Import character failed: {e}")
            return False, f"导入失败: {str(e)}", None

if __name__ == "__main__":
    cm = ConfigManager()
    print("配置加载成功")
    print(f"当前角色: {cm.get_current_character().get('name')}")
    print(f"所有角色: {cm.get_all_characters()}")
