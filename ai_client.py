import json
import urllib.request
import urllib.error
import logging
import os
import datetime
from utils import resource_path

class AIClient:
    def __init__(self, config_manager):
        self.cm = config_manager
        self.logger = logging.getLogger("AIClient")
        self.prompt_templates = self._load_prompt_templates()

    def reload_client(self):
        # 重新加载提示词模板
        self.prompt_templates = self._load_prompt_templates()
    
    def _load_prompt_templates(self):
        """加载提示词模板"""
        # 默认模板（如果文件不存在）
        default_templates = {
            "system_prefix": "Instruction: You are currently roleplaying. Persona: {persona}\n\n",
            "prompts": {
                "water_reminder": "Task: Generate a short reminder to drink water (max 50 words). Current status: {cups}/{target} cups. Tone: Keep the persona, caring but with humor.",
                "meal_reminder": "Task: Remind user it's {meal_time}. Tell them to eat properly (max 40 words). Tone: Caring, like reminding someone important.",
                "sitting_reminder": "Task: Remind user they've been sitting too long. Tell them to stand up and stretch (max 40 words). Tone: Concerned about their health, gentle but firm.",
                "relax_reminder": "Task: Remind user to take a break and relax their eyes/mind (max 40 words). Tone: Warm and caring, like a gentle reminder from someone who cares.",
                "custom_reminder": "Task: Deliver this custom reminder: '{custom_message}'. Remaining times: {remaining_count}. Add a caring personal touch (max 40 words). Tone: Keep the persona.",
                "drink_feedback": "Task: User just drank a cup of water. Current status: {cups}/{target}. Give short feedback (max 30 words). Tone: Encouraging praise with personality.",
                "manual_chat": "Task: Reply to the user. Keep it short and in character. User says: {user_input}",
                "welcome": "Task: User just started the app. It's {time_of_day}. Greet the user (max 40 words). Tone: Warm welcome with personality.",
                "goodbye": "Task: User is closing the app. Say goodbye (max 30 words). Tone: Reluctant but caring farewell.",
                "random_chat": "Task: Tell a short chat or joke (max 50 words). Tone: Keep the persona.",
                "reminder_created": "Task: User just created a new reminder: '{reminder_content}', interval: {interval} minutes, count: {count} times. Acknowledge and respond in character (max 40 words). Tone: Supportive and caring.",
                "medication_reminder": "Task: Remind user to take their medication: '{medication_name}'. Remind them gently and caringly (max 40 words). Tone: Caring and health-conscious.",
                "touch_reaction": "Task: User just touched your '{area_name}'. {area_prompt}. React in character (max 40 words). Tone: Natural physical reaction based on your personality and relationship.",
                "character_switch_goodbye": "Task: User is switching from you to another character: '{next_character_name}'. Say goodbye (max 50 words). Tone: Natural farewell, acknowledge the switch.",
                "character_switch_hello": "Task: User just switched to you from another character: '{prev_character_name}'. Greet them (max 50 words). Tone: Welcoming, acknowledge you're aware they were with someone else.",
                "daily_briefing": "Task: Start the day with a Daily Briefing. 1. State today's date ({date}) and day of week. 2. Briefly mention weather (if provided: {weather}). 3. Give a short encouraging quote or tip for the day. Tone: Energetic and supportive."
            }
        }
        
        # 优先使用当前目录的模板文件（用户自定义），否则使用打包的模板
        template_file = "prompt_templates.json"
        if not os.path.exists(template_file):
            template_file = resource_path("prompt_templates.json")
        
        if not os.path.exists(template_file):
            self.logger.info("Prompt template file not found, using defaults")
            return default_templates
        
        try:
            with open(template_file, 'r', encoding='utf-8') as f:
                templates = json.load(f)
                self.logger.info(f"Loaded prompt templates from: {template_file}")
                return templates
        except Exception as e:
            self.logger.error(f"Failed to load prompt templates: {e}")
            return default_templates

    def _get_url(self, endpoint):
        base_url = self.cm.get("api_base_url").rstrip('/')
        if base_url.endswith('/v1'):
            return f"{base_url}/{endpoint}"
        return f"{base_url}/v1/{endpoint}" if not base_url.endswith(endpoint) else base_url

    def _make_request(self, url, payload=None, method='POST'):
        api_key = self.cm.get("api_key")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" # 伪装成浏览器
        }
        
        data = json.dumps(payload).encode('utf-8') if payload else None
        
        self.logger.info(f"Making request to: {url}")
        if payload:
            safe_payload = payload.copy()
            if 'messages' in safe_payload:
                self.logger.debug(f"Prompt: {safe_payload['messages']}")

        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=30) as response: # 增加超时时间
                resp_data = response.read()
                self.logger.info(f"Response status: {response.status}")
                # 记录原始返回数据，以便排查
                raw_response = resp_data.decode('utf-8')
                self.logger.debug(f"Raw API Response: {raw_response[:500]}...") # 只记录前500字符
                return json.loads(raw_response)
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode('utf-8')
            self.logger.error(f"HTTP Error {e.code}: {err_msg}")
            raise Exception(f"HTTP {e.code}: {err_msg}")
        except Exception as e:
            self.logger.error(f"Request failed: {str(e)}")
            raise e

    def get_models(self):
        """Fetches available models from the API"""
        base_url = self.cm.get("api_base_url").rstrip('/')
        if base_url.endswith('/chat/completions'):
            base_url = base_url.replace('/chat/completions', '')
        
        url = f"{base_url}/models"

        self.logger.info(f"Fetching models from {url}")
        try:
            result = self._make_request(url, method='GET')
            return [m['id'] for m in result.get('data', [])]
        except Exception as e:
            self.logger.error(f"Failed to get models: {e}")
            return []

    def get_reminder_message(self, reminder_type="water", **kwargs):
        """获取不同类型的提醒消息
        reminder_type: water, meal, sitting, relax, custom
        """
        return self._generate_message("reminder", reminder_type=reminder_type, **kwargs)

    def get_chat_message(self):
        return self._generate_message("chat")
        
    def get_drink_feedback(self):
        return self._generate_message("feedback")

    def chat_with_user(self, user_input):
        # 1. 记录用户输入
        self.cm.add_chat_history("user", user_input)
        
        # 2. 生成回复
        response = self._generate_message("manual_chat", user_input)
        
        # 3. 记录AI回复
        self.cm.add_chat_history("assistant", response)
        
        return response

    def get_welcome_message(self, offline_info=None):
        """获取欢迎消息
        offline_info: 离线信息字典，包含 is_first_time, offline_seconds, offline_text
        """
        kwargs = {}
        if offline_info:
            kwargs["offline_info"] = offline_info
        return self._generate_message("welcome", **kwargs)

    def get_goodbye_message(self):
        return self._generate_message("goodbye")
    
    def get_reminder_created_message(self, reminder_content, interval, count):
        """获取用户创建提醒后的AI响应"""
        return self._generate_message("reminder_created", 
                                       reminder_content=reminder_content,
                                       interval=interval, 
                                       count=count)
    
    def get_touch_reaction(self, area_name, area_prompt):
        """获取触摸反应消息
        area_name: 触摸区域名称 (如：头部、脸颊等)
        area_prompt: 自定义的触摸提示词
        """
        return self._generate_message("touch_reaction", 
                                       area_name=area_name,
                                       area_prompt=area_prompt)
    
    def get_character_switch_goodbye(self, next_character_info):
        """获取角色切换时的告别消息
        next_character_info: 即将切换到的角色信息 dict {name, persona, user_identity}
        """
        return self._generate_message("character_switch_goodbye",
                                       next_character_info=next_character_info)
    
    def get_character_switch_hello(self, prev_character_info):
        """获取角色切换后的欢迎消息
        prev_character_info: 上一个角色的信息 dict {name, persona, user_identity}
        """
        return self._generate_message("character_switch_hello",
                                       prev_character_info=prev_character_info)

    def get_daily_briefing_message(self, date_str, weekday_str, weather_info=""):
        return self._generate_message("daily_briefing", 
                                      date=date_str, 
                                      weekday=weekday_str, 
                                      weather=weather_info)

    def _generate_message(self, msg_type, user_input=None, reminder_type=None, **kwargs):
        api_key = self.cm.get("api_key")
        base_url = self.cm.get("api_base_url")

        if not api_key or not base_url:
            self.logger.warning("API key or URL missing")
            return "请先在设置中配置 API URL 和 Key 哦。"

        persona = self.cm.get("persona")
        user_identity = self.cm.get("user_identity")
        model = self.cm.get("model")
        user_name = self.cm.get("user_name") or "用户"  # 获取用户名称，默认为"用户"
        char_name = self.cm.get_current_character().get("name", "角色") if self.cm.get_current_character() else "角色"

        # --- Lorebook 处理 ---
        active_lore = []
        lorebook = self.cm.get("lorebook") or []
        
        for entry in lorebook:
            is_active = False
            if entry.get("type") == "always":
                is_active = True
            elif entry.get("type") == "keyword" and user_input:
                # 检查关键词
                keywords = entry.get("keywords", "").replace("，", ",").split(",")
                for kw in keywords:
                    kw = kw.strip()
                    if kw and kw in user_input:
                        is_active = True
                        self.logger.info(f"Lorebook triggered by keyword: {kw}")
                        break
            
            if is_active:
                active_lore.append(entry.get("content", ""))
        
        lorebook_content = "\\n".join(active_lore) if active_lore else "无"
        # ---------------------
        
        # --- 纪念日检测 ---
        anniversary_note = ""
        today_anniversaries = self.cm.get_today_anniversaries()
        if today_anniversaries:
            anniversary_texts = []
            for anniv in today_anniversaries:
                anniv_type = anniv.get("type", "custom")
                title = anniv.get("title", "")
                notes = anniv.get("notes", "")
                
                if anniv_type == "birthday":
                    anniversary_texts.append(f"今天是{title}的生日")
                else:
                    anniversary_texts.append(f"今天是{title}")
                
                if notes:
                    anniversary_texts.append(f"备注：{notes}")
            
            if anniversary_texts:
                anniversary_note = "\\n\\n以下是今天的特殊纪念日，你需要在回复中考虑这些信息：\\n<anniversaries>\\n" + "\\n".join(anniversary_texts) + "\\n</anniversaries>"
                self.logger.info(f"Today's anniversaries: {today_anniversaries}")
        # ---------------------
        
        # --- 健康状态检测 ---
        health_note = ""
        period_status = self.cm.get_period_status()
        
        if period_status.get("status") == "in_period":
            # 正在生理期内
            day = period_status.get("period_day", 1)
            health_note += f"\\n\\n<health_status>\\n[生理期状态] 用户正处于生理期第{day}天。你需要表现出更多的关心和体贴，提醒她注意保暖、多喝热水、避免剧烈运动。语气要温柔体贴。\\n</health_status>"
            self.logger.info(f"Period status: Day {day}")
            
        elif period_status.get("status") == "approaching":
            # 即将到来
            days = period_status.get("days_until", 0)
            health_note += f"\\n\\n<health_status>\\n[生理期预警] 预计{days}天后用户的生理期将到来。可以适当提醒她提前准备卫生用品，注意饮食和休息。\\n</health_status>"
            self.logger.info(f"Period approaching in {days} days")
        # ---------------------
        
        prompts = self.prompt_templates.get("prompts", {})
        
        # 准备变量字典
        variables = {
            "persona": persona,
            "user": user_name,  # 用户名称
            "char": char_name,  # 角色名称
            "cups": self.cm.get("cups_drunk_today"),
            "target": self.cm.get("daily_target_cups"),
            "user_input": user_input if user_input else "Hello",
            "hour": datetime.datetime.now().hour,
            "reminder_content": kwargs.get("reminder_content", ""),
            "interval": kwargs.get("interval", 0),
            "count": kwargs.get("count", 0),
            "medication_name": kwargs.get("medication_name", ""),
            "area_name": kwargs.get("area_name", "某个部位"),
            "area_prompt": kwargs.get("area_prompt", ""),
            "offline_text": "",
            "is_first_time": False,
            "next_character_name": "",
            "prev_character_name": ""
        }
        
        # 处理离线信息
        offline_info = kwargs.get("offline_info")
        if offline_info:
            variables["is_first_time"] = offline_info.get("is_first_time", False)
            variables["offline_text"] = offline_info.get("offline_text", "")
            variables["offline_seconds"] = offline_info.get("offline_seconds", 0)
        
        # 计算时间段
        hour = variables["hour"]
        variables["time_of_day"] = "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "evening"
        
        # 生成表情列表
        expressions_config = self.cm.get("expressions") or {}
        mappings = expressions_config.get("mappings", {})
        if mappings:
            expressions_list = ", ".join([f"[{keyword}]" for keyword in mappings.keys()])
            variables["expressions"] = expressions_list
            self.logger.info(f"Available expressions: {expressions_list}")
        else:
            variables["expressions"] = "暂无配置表情"
            self.logger.info("No expressions configured")
        
        # 根据消息类型选择模板 (Task)
        if msg_type == "reminder":
            if reminder_type == "water":
                template = prompts.get("water_reminder", {})
            elif reminder_type == "meal":
                template = prompts.get("meal_reminder", {})
                variables["meal_time"] = kwargs.get("meal_time", "meal time")
            elif reminder_type == "sitting":
                template = prompts.get("sitting_reminder", {})
            elif reminder_type == "relax":
                template = prompts.get("relax_reminder", {})
            elif reminder_type == "medication":
                template = prompts.get("medication_reminder", {})
                variables["medication_name"] = kwargs.get("medication_name", "药品")
            elif reminder_type == "custom":
                template = prompts.get("custom_reminder", {})
                variables["custom_message"] = kwargs.get("custom_message", "提醒时间到了")
                variables["remaining_count"] = kwargs.get("remaining_count", 0)
            else:
                template = "Task: General reminder (max 40 words)."
            
        elif msg_type == "feedback":
            template = prompts.get("drink_feedback", {})

        elif msg_type == "manual_chat":
            template = prompts.get("manual_chat", {})
            
        elif msg_type == "welcome":
            template = prompts.get("welcome", {})

        elif msg_type == "goodbye":
            template = prompts.get("goodbye", {})
        
        elif msg_type == "reminder_created":
            template = prompts.get("reminder_created", {})
        
        elif msg_type == "touch_reaction":
            template = prompts.get("touch_reaction", {})
        
        elif msg_type == "character_switch_goodbye":
            template = prompts.get("character_switch_goodbye", {})
            next_char_info = kwargs.get("next_character_info", {})
            variables["next_character_name"] = next_char_info.get("name", "另一个角色")
        
        elif msg_type == "character_switch_hello":
            template = prompts.get("character_switch_hello", {})
            prev_char_info = kwargs.get("prev_character_info", {})
            variables["prev_character_name"] = prev_char_info.get("name", "上一个角色")

        elif msg_type == "daily_briefing":
            template = prompts.get("daily_briefing", {})
            variables["date"] = kwargs.get("date", "")
            variables["weekday"] = kwargs.get("weekday", "")
            variables["weather"] = kwargs.get("weather", "未知")

        else:  
            template = prompts.get("random_chat", {})
        
        # 获取Task文本
        if isinstance(template, dict):
            template_text = template.get("template", str(template))
        else:
            template_text = str(template)
        
        try:
            task_content = template_text.format(**variables)
        except KeyError as e:
            self.logger.warning(f"Template variable missing: {e}, using original template")
            task_content = template_text

        # --- History 处理 ---
        # 优化：不将历史记录作为 Prompt 文本的一部分，而是作为独立的消息（后续处理）
        # 这里暂时只准备 System Prompt 的上下文内容
        
        # --- 构建最终 Prompt ---
        # 处理角色切换的特殊情况
        switch_context = ""
        if msg_type == "character_switch_goodbye":
            next_char_info = kwargs.get("next_character_info", {})
            switch_context = f"""
<character_switch_context>
用户即将切换到另一个角色，以下是那个角色的信息：
角色名: {next_char_info.get("name", "未知")}
角色设定: {next_char_info.get("persona", "无")}
用户在那个角色下的身份: {next_char_info.get("user_identity", "无")}
</character_switch_context>"""
        
        elif msg_type == "character_switch_hello":
            prev_char_info = kwargs.get("prev_character_info", {})
            switch_context = f"""
<character_switch_context>
用户刚从另一个角色切换到你这里，以下是上一个角色的信息：
角色名: {prev_char_info.get("name", "未知")}
角色设定: {prev_char_info.get("persona", "无")}
用户在那个角色下的身份: {prev_char_info.get("user_identity", "无")}
</character_switch_context>"""
        
        # 构造系统提示词 (System Prompt)
        system_content = f"""你正在进行角色扮演。
角色名: {char_name}
人设: {persona}
用户: {user_name}
用户身份: {user_identity}

背景知识(Lorebook):
{lorebook_content}

{anniversary_note}
{health_note}
{switch_context}

在生成回复时，你可以使用[xxx]来表示表情，目前有以下表情：
{variables["expressions"]}

请始终保持角色人设，基于你和用户的关系自然对话。
"""

        if base_url.endswith('/chat/completions'):
            url = base_url
        else:
            url = f"{base_url.rstrip('/')}/chat/completions"

        # 构建 Messages 列表 (System + History + Current Task)
        messages = [
            {"role": "system", "content": system_content}
        ]

        # 插入历史记录
        if msg_type == "manual_chat":
            history = self.cm.get_chat_history()
            # 过滤掉刚刚加入的最后一条用户消息（因为那是本次的任务输入）
            if len(history) > 1:
                # 从配置读取最大历史消息数
                max_history = self.cm.get("max_history_messages") or 10
                # 只取最近的 N 条历史记录，避免 Token 爆炸
                # -max_history-1 表示倒数第(max_history+1)条，-1 表示倒数第2条（排除最后一条）
                start_index = -(max_history + 1)
                recent_history = history[max(0, start_index):-1]
                self.logger.info(f"Sending {len(recent_history)} history messages (max: {max_history})")
                for msg in recent_history:
                    # 确保 role 是 API 支持的格式 (user/assistant)
                    role = "user" if msg["role"] == "user" else "assistant"
                    messages.append({"role": role, "content": msg["content"]})

        # 插入当前任务
        messages.append({"role": "user", "content": f"任务: {task_content}"})

        # 极限精简的 Payload
        payload = {
            "model": model,
            "messages": messages,
            "stream": False
        }

        try:
            result = self._make_request(url, payload)
            
            # 增加对不同返回结构的容错处理
            if 'choices' in result and len(result['choices']) > 0:
                choice = result['choices'][0]
                if 'message' in choice and 'content' in choice['message']:
                    content = choice['message']['content'].strip()
                    self.logger.info(f"AI Response: {content}")
                    return content if content else "(AI 似乎无话可说，请检查日志)"
                else:
                    self.logger.error(f"Unexpected response structure: {result}")
                    return "(AI 返回格式异常，请检查日志)"
            else:
                self.logger.error(f"No choices in response: {result}")
                return "(AI 未返回有效内容，请检查日志)"
            
        except Exception as e:
            self.logger.error(f"Generation failed: {e}")
            return f"AI请求失败: {str(e)[:30]}..." 

if __name__ == "__main__":
    from config_manager import ConfigManager
    cm = ConfigManager()
    ai = AIClient(cm)
