import tkinter as tk
from tkinter import ttk, messagebox, Menu, simpledialog, filedialog
import customtkinter as ctk
import threading
from datetime import datetime, timedelta
import os
import shutil
import time
import uuid
import webbrowser
from config_manager import ConfigManager
from ai_client import AIClient
import logging
import sys
from utils import resource_path, setup_logging, get_weather_info

# 托盘图标支持
import pystray
from PIL import Image as PILImage
from PIL import ImageTk, ImageDraw, ImageFont

# 设置 CustomTkinter 主题
ctk.set_appearance_mode("System")  # 跟随系统 (Light/Dark)
ctk.set_default_color_theme("blue")  # 主题颜色

# 定义透明色（必须是一个你立绘里没用到的颜色）
TRANSPARENT_COLOR = '#ff00ff'  # 亮粉色

class InputBox(ctk.CTkToplevel):
    def __init__(self, parent, x, y, callback, continuous_mode=False, config_manager=None):
        super().__init__(parent)
        self.callback = callback
        self.continuous_mode = continuous_mode
        self.cm = config_manager
        
        # 读取样式配置
        appearance = self.cm.get("appearance") if self.cm else {}
        input_style = appearance.get("input_box", {})
        
        bg_color = input_style.get("background_color", "#FFFFFF")
        border_color = input_style.get("border_color", "#E5E5E5")
        text_color = input_style.get("text_color", "#333333")
        button_color = input_style.get("button_color", "#7EA0B7")
        button_hover = input_style.get("button_hover_color", "#6C8EA4")
        corner_radius = input_style.get("corner_radius", 30)
        font_size = input_style.get("font_size", 13)
        
        # 无边框，置顶
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        
        # 尺寸
        width = 340
        height = 60
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.config(bg="white")
        
        # 为了实现更好的圆角效果，使用透明背景
        try:
            self.wm_attributes('-transparentcolor', '#000001')
            self.config(bg='#000001')
        except:
            pass # Mac/Linux不需要这个Hack
            
        # 主容器
        self.frame = ctk.CTkFrame(
            self, 
            corner_radius=corner_radius, 
            fg_color=bg_color,
            bg_color="#000001",
            border_width=1,
            border_color=border_color
        )
        self.frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        # 拖动支持
        self.frame.bind("<Button-1>", self.start_move)
        self.frame.bind("<B1-Motion>", self.do_move)
        
        # 输入框
        self.entry = ctk.CTkEntry(
            self.frame, 
            placeholder_text="想和我说什么？" if not continuous_mode else "输入内容 (Esc退出)...",
            font=("Microsoft YaHei UI", font_size),
            border_width=0,
            fg_color="transparent",
            text_color=text_color,
            placeholder_text_color="#AAAAAA",
            height=40
        )
        self.entry.pack(side="left", fill="both", expand=True, padx=(20, 5), pady=10)
        self.entry.focus_set()
        
        # 发送按钮
        self.btn = ctk.CTkButton(
            self.frame, 
            text="➤", 
            width=40, 
            height=40, 
            corner_radius=20,
            font=("Arial", 16),
            fg_color=button_color,
            hover_color=button_hover,
            command=self.send
        )
        self.btn.pack(side="right", padx=(5, 10), pady=10)
        
        self.entry.bind("<Return>", lambda e: self.send())
        
        if not self.continuous_mode:
            self.bind("<Escape>", lambda e: self.destroy())
            self.bind("<FocusOut>", lambda e: self.destroy())
        else:
            self.bind("<Escape>", lambda e: self.destroy())
            # 持续模式下不绑定 FocusOut 关闭

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.winfo_x() + deltax
        y = self.winfo_y() + deltay
        self.geometry(f"+{x}+{y}")

    def send(self):
        text = self.entry.get().strip()
        if text:
            self.callback(text)
            self.entry.delete(0, 'end') # 清空输入框
            
        if not self.continuous_mode:
            self.destroy()
        else:
            # 持续模式：发送后不关闭，保持焦点
            self.entry.focus_set()

class DesktopPetApp:
    def __init__(self, root):
        self.root = root
        self.cm = ConfigManager()
        self.ai_client = AIClient(self.cm)
        
        # 窗口基本设置
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.wm_attributes('-transparentcolor', TRANSPARENT_COLOR)
        self.root.config(bg=TRANSPARENT_COLOR)
        
        # 屏幕适配与初始位置
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        # 加宽窗口，给气泡留足够的左侧空间
        self.root.geometry(f"600x500+{screen_width-650}+{screen_height-600}")
        
        # 状态变量
        self.timer_running = True
        self.bubble_timer = None
        self.is_closing = False
        self.tray_icon = None
        
        # 多种提醒的下次触发时间
        self.next_reminders = {
            "water": None,
            "meal": None,
            "sitting": None,
            "relax": None,
            "medication": {}  # {med_id: next_time}
        }
        self.next_chat_time = None
        
        # 气泡图片引用（防止被垃圾回收）
        self.bubble_photo = None
        
        # 表情系统
        self.expressions = {}  # 存储所有表情立绘
        self.current_expression = "default"  # 当前表情
        self.expression_restore_timer = None  # 表情恢复定时器
        
        # AI请求锁定状态
        self.is_waiting_ai_response = False
        self.ai_lock = threading.Lock()
        
        # 加载资源
        self.load_assets()
        
        # 启动托盘图标
        self.setup_tray()
        
        # 构建 UI
        self.setup_ui()
        
        # 绑定事件
        self.bind_events()
        
        # 启动逻辑
        self.schedule_all_reminders()
        self.check_schedule()
        
        # 初始打招呼
        self.show_bubble("连接中...", duration=0)
        threading.Thread(target=self._async_ai_welcome, daemon=True).start()
        
        # 检查每日早报
        self.root.after(5000, self.check_daily_briefing)

    def load_assets(self):
        """加载默认立绘和所有表情立绘"""
        # 获取当前角色
        current_char = self.cm.get_current_character()
        if not current_char:
            logging.error("No current character found!")
            return
        
        # 获取表情配置
        expressions_config = self.cm.get("expressions") or {}
        
        # 获取默认立绘：优先使用 expressions.default，否则使用 avatar
        default_img = expressions_config.get("default", "")
        if not default_img:
            default_img = current_char.get("avatar", "character.png")
            logging.info(f"No expressions.default, using avatar: {default_img}")
        self.photo = self._load_single_image(default_img)
        self.expressions["default"] = self.photo
        
        # 加载所有表情立绘
        mappings = expressions_config.get("mappings", {})
        for emotion_tag, filename in mappings.items():
            img = self._load_single_image(filename)
            if img:
                self.expressions[emotion_tag] = img
                logging.info(f"Loaded expression: {emotion_tag} -> {filename}")
            else:
                logging.warning(f"Failed to load expression: {emotion_tag} -> {filename}")
    
    def _load_single_image(self, filename):
        """加载单个立绘图片
        
        重要说明：
        - tkinter使用-transparentcolor技术实现透明窗口
        - 该技术将亮粉色(#ff00ff)像素视为透明
        - PNG边缘的半透明像素会与粉色背景混合，产生粉色边缘
        - 解决方案：对alpha通道进行二值化处理（牺牲抗锯齿，换取无粉边）
        
        最佳实践：
        - 在Photoshop中预处理PNG，去除半透明像素（参见PNG处理指南.md）
        - 这样可以获得最佳显示效果
        """
        # 优先使用当前目录的自定义立绘，否则使用打包的默认立绘
        img_path = filename
        if not os.path.exists(img_path):
            img_path = resource_path(filename)
        
        if not os.path.exists(img_path):
            return None
            
        try:
            pil_image = PILImage.open(img_path)
            
            # 确保图像为RGBA模式（支持透明度）
            if pil_image.mode != 'RGBA':
                pil_image = pil_image.convert('RGBA')
            
            # 缩放处理 - 使用高质量的LANCZOS算法
            if pil_image.height > 400:
                ratio = 400 / pil_image.height
                new_width = int(pil_image.width * ratio)
                pil_image = pil_image.resize((new_width, 400), PILImage.Resampling.LANCZOS)
            
            # 处理Alpha通道 - 移除半透明像素以避免粉色边缘
            # 这是tkinter透明窗口的必要处理
            if pil_image.mode == 'RGBA':
                r, g, b, a = pil_image.split()
                
                # 二值化Alpha通道：移除所有半透明像素
                # alpha > 200: 保持不透明
                # alpha <= 200: 变为完全透明
                # 阈值200而不是128可以保留更多边缘细节
                a = a.point(lambda x: 255 if x > 200 else 0)
                
                # 应用处理后的Alpha通道
                pil_image.putalpha(a)
            
            return ImageTk.PhotoImage(pil_image)
        except Exception as e:
            logging.error(f"Error loading image {filename}: {e}")
            return None
        
    def setup_tray(self):
        # 准备托盘图标 - 优先使用当前目录，否则使用打包的资源
        icon_path = "icon.png"
        if not os.path.exists(icon_path):
            icon_path = resource_path("icon.png")
        
        if os.path.exists(icon_path):
            image = PILImage.open(icon_path)
        else:
            # 如果没有 icon.png，使用 character.png 的缩略图
            # 优先使用当前角色的 avatar
            current_char = self.cm.get_current_character()
            if current_char and current_char.get("avatar"):
                char_path = current_char.get("avatar")
            else:
                char_path = "character.png"
                if not os.path.exists(char_path):
                    char_path = resource_path("character.png")
            
            if os.path.exists(char_path):
                image = PILImage.open(char_path)
            else:
                # 最后的备选方案：创建一个色块
                image = PILImage.new('RGB', (64, 64), color='skyblue')
        
        # 创建菜单
        menu = pystray.Menu(
            pystray.MenuItem("显示/隐藏", self.toggle_visibility),
            pystray.MenuItem("退出", self.force_quit)
        )
        
        self.tray_icon = pystray.Icon("ProjectAnmicius", image, "Project Anmicius", menu)
        # 在独立线程运行托盘，避免阻塞 tkinter 主循环
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def toggle_visibility(self, icon, item):
        if self.root.winfo_viewable():
            self.root.withdraw()
        else:
            self.root.deiconify()

    def force_quit(self, icon, item):
        # 保存退出时间
        self.save_exit_time()
        self.tray_icon.stop()
        self.root.quit()
        sys.exit()

    def setup_ui(self):
        # 先恢复窗口到默认高度和位置，避免立绘被裁剪
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        default_x = screen_width - 650
        default_y = screen_height - 600
        self.root.geometry(f"600x500+{default_x}+{default_y}")
        
        if hasattr(self, 'canvas'):
            self.canvas.destroy()
            
        self.canvas = tk.Canvas(self.root, width=600, height=500, 
                                bg=TRANSPARENT_COLOR, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # 使用当前表情的立绘
        current_photo = self.expressions.get(self.current_expression, self.photo)
        
        if current_photo:
            # 立绘往右移，给左侧气泡留足够空间
            self.canvas.create_image(370, 480, image=current_photo, anchor=tk.S, tags="character")
        else:
            # 缺省立绘也要对应右移
            self.canvas.create_oval(270, 250, 470, 450, fill="#FFB6C1", outline="white", width=3, tags="character")
            self.canvas.create_text(370, 350, text="立绘缺失\n请放入\ncharacter.png", fill="white", justify=tk.CENTER, font=("微软雅黑", 12, "bold"))
    
    def set_expression(self, emotion_tag):
        """切换表情"""
        if emotion_tag in self.expressions:
            self.current_expression = emotion_tag
            
            # 获取当前立绘的位置（如果存在）
            char_x, char_y = 370, 480  # 默认位置
            try:
                items = self.canvas.find_withtag("character")
                if items:
                    # 获取第一个 character 项的坐标
                    coords = self.canvas.coords(items[0])
                    if coords:
                        char_x, char_y = coords[0], coords[1]
            except Exception as e:
                logging.error(f"Error getting character position: {e}")
            
            # 更新画布上的立绘
            self.canvas.delete("character")
            current_photo = self.expressions[emotion_tag]
            if current_photo:
                self.canvas.create_image(char_x, char_y, image=current_photo, anchor=tk.S, tags="character")
            logging.info(f"Expression changed to: {emotion_tag}")
        else:
            logging.warning(f"Expression not found: {emotion_tag}")
    
    def restore_default_expression(self):
        """恢复默认表情"""
        if self.current_expression != "default":
            self.set_expression("default")
            logging.info("Expression restored to default")
    
    def parse_expression_tags(self, text):
        """解析文本中的表情标签，返回(清理后的文本, 表情标签)"""
        import re
        # 匹配[xxx]格式的表情标签
        pattern = r'\[([^\]]+)\]'
        matches = re.findall(pattern, text)
        
        # 移除所有表情标签
        cleaned_text = re.sub(pattern, '', text).strip()
        
        # 返回第一个匹配的表情（如果有多个，只用第一个）
        emotion = matches[0] if matches else None
        
        return cleaned_text, emotion

    def _load_font(self, size=12):
        """加载字体（支持系统字体和自定义字体文件）"""
        # 获取字体配置
        appearance = self.cm.get("appearance") or {}
        bubble_style = appearance.get("bubble", {})
        
        font_type = bubble_style.get("font_type", "custom")  # "system" 或 "custom"
        font_name = bubble_style.get("font_name", "Microsoft YaHei UI")
        font_file = bubble_style.get("font_file", "")
        
        logging.info(f"加载字体 - 类型: {font_type}, 名称: {font_name}, 文件: {font_file}")
        
        # 1. 如果是自定义字体文件
        if font_type == "custom" and font_file:
            # 规范化路径（处理正斜杠和反斜杠）
            font_file_normalized = os.path.normpath(font_file)
            logging.info(f"尝试加载自定义字体文件: {font_file_normalized}")
            
            if os.path.exists(font_file_normalized):
                try:
                    font = ImageFont.truetype(font_file_normalized, size)
                    logging.info(f"✓ 成功加载自定义字体: {font_file_normalized}")
                    return font
                except Exception as e:
                    logging.error(f"✗ 无法加载自定义字体文件 {font_file_normalized}: {e}")
            else:
                logging.error(f"✗ 字体文件不存在: {font_file_normalized}")
                # 尝试相对路径
                if not os.path.isabs(font_file):
                    relative_path = os.path.join(os.path.dirname(__file__), font_file)
                    if os.path.exists(relative_path):
                        try:
                            font = ImageFont.truetype(relative_path, size)
                            logging.info(f"✓ 使用相对路径加载字体: {relative_path}")
                            return font
                        except Exception as e:
                            logging.error(f"✗ 相对路径也失败: {e}")
        
        # 2. 如果是系统字体
        if font_type == "system" and font_name:
            # 系统字体映射表
            font_map = {
                "Microsoft YaHei UI": "msyh.ttc",
                "Microsoft YaHei": "msyh.ttc",
                "SimHei": "simhei.ttf",
                "SimSun": "simsun.ttc",
                "KaiTi": "simkai.ttf",
                "FangSong": "simfang.ttf",
                "Arial": "arial.ttf",
                "Times New Roman": "times.ttf",
                "Courier New": "cour.ttf"
            }
            
            font_file_name = font_map.get(font_name, "msyh.ttc")
            
            try:
                # 尝试从系统字体目录加载
                system_font_path = os.path.join("C:\\Windows\\Fonts", font_file_name)
                if os.path.exists(system_font_path):
                    return ImageFont.truetype(system_font_path, size)
            except Exception as e:
                logging.warning(f"无法加载系统字体 {font_name}: {e}")
            
            # 尝试直接使用字体名称
            try:
                return ImageFont.truetype(font_name, size)
            except:
                pass
        
        # 3. 回退：使用项目自带的字体
        font_path = "ChillRoundFRegular.ttf"
        if not os.path.exists(font_path):
            font_path = resource_path("ChillRoundFRegular.ttf")
        
        try:
            if os.path.exists(font_path):
                return ImageFont.truetype(font_path, size)
        except Exception as e:
            logging.warning(f"无法加载项目字体: {e}")
        
        # 4. 最后回退：系统默认字体
        try:
            return ImageFont.truetype("msyh.ttc", size)  # 微软雅黑
        except:
            return ImageFont.load_default()
    
    def _hex_to_rgb(self, hex_color):
        """将hex颜色转换为RGB元组"""
        hex_color = hex_color.lstrip('#')
        try:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        except:
            return (255, 255, 255)  # 默认白色
    
    def adjust_window_height(self, required_height):
        """动态调整窗口高度以适应内容，保持立绘在屏幕上的位置视觉不变"""
        target_height = int(max(500, required_height))
        current_height = self.root.winfo_height()
        
        # 初始启动时 winfo_height 可能为 1
        if current_height < 500: current_height = 500
        
        if target_height == current_height:
            return

        diff = target_height - current_height
        
        # 1. 调整窗口 Geometry (向上生长)
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        new_y = y - diff
        
        self.root.geometry(f"600x{target_height}+{x}+{new_y}")
        
        # 2. 移动立绘 (向下移动以抵消窗口上移，保持屏幕位置不变)
        self.canvas.move("character", 0, diff)
        
        self.root.update_idletasks()
        
    def restore_window_height(self):
        """恢复窗口默认高度"""
        self.adjust_window_height(500)

    def create_bubble(self, text):
        """绘制气泡（无尾巴、纯绘制，避免边框变粗和重叠）"""
        logging.info(f"create_bubble called with text: {text[:50] if text else 'EMPTY'}...")
        
        self.canvas.delete("bubble_image")
        if not text:
            logging.info("create_bubble: text is empty, restoring window height")
            self.restore_window_height()
            return
        
        logging.info(f"create_bubble: proceeding to draw bubble with text length: {len(text)}")

        # ========== 获取立绘当前位置 (动态) ==========
        char_bottom_y = 480 # 默认值
        char_top_y = 280
        char_height = 200
        char_left_edge = 270 # Default fallback
        
        try:
            # 查找 tag 为 character 的项
            items = self.canvas.find_withtag("character")
            if items:
                # 找最底部的边界
                max_y = 0
                min_x = 1000
                for item in items:
                    bbox = self.canvas.bbox(item)
                    if bbox:
                        if bbox[3] > max_y: max_y = bbox[3]
                        if bbox[0] < min_x: min_x = bbox[0]
                
                if max_y > 0:
                    char_bottom_y = max_y
                    # 估算高度：如果是图片，高度准确；如果是 fallback，也是准确的
                    # 我们主要关心头部位置
                    # 假设立绘高度大概在 200-400 之间
                    if self.photo:
                        char_height = self.photo.height()
                    else:
                        char_height = 200
                    
                    char_top_y = char_bottom_y - char_height
                    # 修正左边界 (如果是图片，bbox[0]就是左边界)
                    # 但是立绘可能有透明边距... 不过这里用 bbox 应该够了
                    char_left_edge = min_x
        except Exception as e:
            logging.error(f"Error getting character bbox: {e}")

        # ========== 配置 - 从config读取 ==========
        appearance = self.cm.get("appearance") or {}
        bubble_style = appearance.get("bubble", {})
        
        font_size = bubble_style.get("font_size", 14)
        pil_font = self._load_font(font_size)
        ascent, descent = pil_font.getmetrics()
        
        # 行高：增大防止截断
        line_height = ascent + descent + 10
        
        # 内边距
        padding_x = bubble_style.get("padding_x", 30)
        padding_y = bubble_style.get("padding_y", 28)
        
        # 颜色 - 将hex转为RGB元组
        border_color = self._hex_to_rgb(bubble_style.get("border_color", "#646464"))
        fill_color = self._hex_to_rgb(bubble_style.get("background_color", "#FFFFFF"))
        text_color = self._hex_to_rgb(bubble_style.get("text_color", "#323232"))
        corner_radius = bubble_style.get("corner_radius", 14)
        border_width = bubble_style.get("border_width", 1)

        # ========== 可用空间计算 ==========
        # 气泡在立绘左侧，预留 10px 间隙
        available_space = char_left_edge - 10
        if available_space < 150:
            available_space = 150  # 保底

        # 最大文字宽度
        # 用户要求不要限制长度，但为了换行，我们需要一个宽度基准
        # 这里的 max_text_width 主要是决定何时换行
        # 我们可以稍微放宽，但不能太宽导致覆盖立绘
        max_text_width = available_space - padding_x * 2
        max_text_width = max(max_text_width, 160) 
        max_text_width = min(max_text_width, 400) # 稍微放宽到 400

        # ========== 文本换行与尺寸计算 ==========
        temp_img = PILImage.new('RGBA', (1, 1))
        temp_draw = ImageDraw.Draw(temp_img)

        lines = []
        current = ""
        for ch in text:
            test = current + ch
            w = temp_draw.textbbox((0, 0), test, font=pil_font)[2]
            if ch == '\n':
                lines.append(current)
                current = ""
            elif w > max_text_width and current:
                lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)

        text_w = max(temp_draw.textbbox((0, 0), line, font=pil_font)[2] for line in lines) if lines else 0
        text_h = len(lines) * line_height

        # ========== 气泡尺寸 ==========
        bubble_w = int(text_w + padding_x * 2)
        bubble_h = int(text_h + padding_y * 2)
        
        bubble_w = max(bubble_w, 180)
        bubble_h = max(bubble_h, 100)

        # ========== 动态调整窗口高度 ==========
        # 使用绝对高度公式计算
        # H >= 气泡半高 + 头部位置(从底部算) + 顶部留白
        # 头部位置 = 20(底部留白) + char_height * 0.8
        # 顶部留白 = 5
        required_H = 25 + char_height * 0.8 + bubble_h / 2
        
        self.adjust_window_height(required_H)
        
        # 获取调整后的窗口高度，计算最终绘制位置
        new_H = self.root.winfo_height()
        if new_H == 1: new_H = 500 # 防止未更新
        
        # 重新计算头部位置
        head_center_y = new_H - 20 - char_height * 0.8
        
        canvas_y = head_center_y - bubble_h / 2
        if canvas_y < 5: canvas_y = 5

        # ========== 最终位置计算 ==========
        # 气泡放在立绘左侧
        gap = 10
        # char_left_edge 还是基于旧坐标计算的吗？
        # 不需要重新计算，因为水平方向没有变化 (adjust_window_height 只改 Y)
        # 且 canvas.move 只改 Y。X 坐标不变。
        
        canvas_x = char_left_edge - bubble_w - gap
        if canvas_x < 5:
            canvas_x = 5
        
        # ========== 绘制气泡 ==========
        # 使用RGBA模式，支持透明背景
        bubble_img = PILImage.new('RGBA', (bubble_w, bubble_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(bubble_img)

        # 背景 - 先画填充，再画边框
        draw.rounded_rectangle([0, 0, bubble_w - 1, bubble_h - 1],
                               radius=corner_radius,
                               fill=fill_color + (255,),  # 添加alpha=255
                               outline=border_color + (255,),
                               width=border_width)

        # 文字
        text_start_y = padding_y + 3 
        for i, line in enumerate(lines):
            y = text_start_y + i * line_height
            draw.text((padding_x, y), line, font=pil_font, fill=text_color + (255,))

        # ========== 显示 ==========
        self.bubble_photo = ImageTk.PhotoImage(bubble_img)
        self.canvas.create_image(int(canvas_x), int(canvas_y),
                                 image=self.bubble_photo, anchor=tk.NW, tags="bubble_image")
        
    def show_bubble(self, text, duration=None):
        # 解析表情标签
        cleaned_text, emotion = self.parse_expression_tags(text)
        
        logging.info(f"show_bubble called - Original: {text[:50]}... | Cleaned: {cleaned_text[:50] if cleaned_text else 'EMPTY'}... | Emotion: {emotion}")
        
        # 如果检测到表情标签，切换表情
        if emotion:
            self.set_expression(emotion)
            
            # 取消之前的恢复定时器
            if self.expression_restore_timer:
                self.root.after_cancel(self.expression_restore_timer)
            
            # 设置新的恢复定时器
            expressions_config = self.cm.get("expressions") or {}
            restore_delay = expressions_config.get("restore_delay", 5) * 1000  # 转换为毫秒
            self.expression_restore_timer = self.root.after(restore_delay, self.restore_default_expression)
        
        # 显示清理后的文本
        self.create_bubble(cleaned_text)
        
        if self.bubble_timer:
            self.root.after_cancel(self.bubble_timer)
            
        # 如果 duration 为 0，表示不自动消失
        if duration == 0:
            return

        # 如果未指定 duration (None)，则根据文本长度动态计算
        if duration is None:
            # 用户阅读速度：1秒10个字 (100ms/字)
            # 策略：基础时间 3秒 + 字数 * 150ms (给予1.5倍的余量)
            base_time = 3000
            per_char_time = 150 
            duration = int(base_time + len(cleaned_text) * per_char_time)
            
            # 限制范围：最少 3秒，最多 60秒
            duration = max(duration, 3000)
            duration = min(duration, 60000)
        
        if duration > 0:
            self.bubble_timer = self.root.after(duration, lambda: self.delete_bubble())

    def delete_bubble(self):
        self.canvas.delete("bubble_image")
        self.restore_window_height()

    def bind_events(self):
        self.canvas.bind("<Button-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.do_move)
        self.canvas.bind("<Button-3>", self.show_context_menu)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)

    def start_move(self, event):
        self.last_x = event.x
        self.last_y = event.y

    def do_move(self, event):
        x = self.root.winfo_x() + (event.x - self.last_x)
        y = self.root.winfo_y() + (event.y - self.last_y)
        self.root.geometry(f"+{x}+{y}")

    def on_double_click(self, event):
        """双击事件 - 先判断是否点击了触摸区域"""
        logging.info(f"on_double_click: Double-click at ({event.x}, {event.y})")
        
        # 狂摸检测 (彩蛋)
        now = time.time()
        if now - getattr(self, 'last_click_time', 0) < 1.0: # 1秒内连续双击
            self.click_count = getattr(self, 'click_count', 0) + 1
        else:
            self.click_count = 1
        self.last_click_time = now
        
        if self.click_count >= 3: # 连续双击3次
            self.click_count = 0
            self.trigger_easter_egg()
            return
        
        # 如果正在等待AI回复，忽略此次双击
        if self.is_waiting_ai_response:
            logging.info("on_double_click: Ignoring - waiting for AI response")
            return
        
        # 检查触摸功能是否启用
        touch_config = self.cm.get("touch_areas")
        logging.info(f"on_double_click: Touch config exists: {touch_config is not None}")
        
        if touch_config:
            enabled = touch_config.get("enabled", False)
            areas_count = len(touch_config.get("areas", []))
            logging.info(f"on_double_click: Touch enabled: {enabled}, Areas: {areas_count}")
            
            if enabled:
                # 尝试检测触摸区域
                touched_area = self.detect_touch_area(event.x, event.y)
                if touched_area:
                    # 点击了触摸区域，触发触摸反应
                    logging.info(f"on_double_click: Triggering touch reaction for '{touched_area.get('name')}'")
                    self.on_touch_area(touched_area)
                    return
                else:
                    logging.info("on_double_click: No touch area detected, falling back to chat")
            else:
                logging.info("on_double_click: Touch disabled, falling back to chat")
        else:
            logging.info("on_double_click: No touch config, falling back to chat")
        
        # 没有点击触摸区域，执行正常闲聊
        logging.info("on_double_click: Triggering normal chat")
        self.trigger_chat()
    
    def detect_touch_area(self, click_x, click_y):
        """检测点击位置是否在某个触摸区域内
        返回: 触摸区域配置 或 None
        """
        # 获取立绘的边界框
        items = self.canvas.find_withtag("character")
        if not items:
            logging.warning("detect_touch_area: No character items found")
            return None
        
        # 获取第一个角色图像的边界框
        char_bbox = self.canvas.bbox(items[0])
        if not char_bbox:
            logging.warning("detect_touch_area: No bbox for character")
            return None
        
        char_left, char_top, char_right, char_bottom = char_bbox
        
        logging.info(f"detect_touch_area: Click at ({click_x}, {click_y})")
        logging.info(f"detect_touch_area: Character bbox: left={char_left}, top={char_top}, right={char_right}, bottom={char_bottom}")
        logging.info(f"detect_touch_area: Character size: width={char_right-char_left}, height={char_bottom-char_top}")
        
        # 检查是否点击在立绘范围内
        if not (char_left <= click_x <= char_right and char_top <= click_y <= char_bottom):
            logging.info("detect_touch_area: Click outside character bounds")
            return None
        
        # 计算点击位置相对于立绘的坐标
        relative_x = click_x - char_left
        relative_y = click_y - char_top
        
        logging.info(f"detect_touch_area: Relative position: ({relative_x}, {relative_y})")
        
        # 检测点击了哪个触摸区域
        touch_config = self.cm.get("touch_areas")
        if not touch_config:
            return None
        
        areas = touch_config.get("areas", [])
        logging.info(f"detect_touch_area: Checking {len(areas)} areas")
        
        for i, area in enumerate(areas):
            ax, ay, aw, ah = area.get("x", 0), area.get("y", 0), area.get("width", 0), area.get("height", 0)
            area_name = area.get("name", f"Area {i}")
            
            logging.info(f"detect_touch_area: Area '{area_name}': x={ax}, y={ay}, w={aw}, h={ah}, range: x[{ax}, {ax+aw}], y[{ay}, {ay+ah}]")
            
            # 判断点击是否在这个区域内
            if ax <= relative_x <= ax + aw and ay <= relative_y <= ay + ah:
                logging.info(f"detect_touch_area: HIT! Area '{area_name}' matched")
                return area
        
        logging.info("detect_touch_area: No area matched")
        return None

    def on_touch_area(self, area):
        """触摸区域被点击"""
        area_name = area.get("name", "某个部位")
        area_prompt = area.get("prompt", "")
        
        logging.info(f"Touch area triggered: {area_name}")
        
        # 锁定AI请求状态
        self.is_waiting_ai_response = True
        
        # 显示加载提示（空文本不会显示气泡，但duration=0可以清除旧气泡）
        self.create_bubble("...")
        
        # 异步调用AI生成触摸反应
        def async_touch_reaction():
            try:
                response = self.ai_client.get_touch_reaction(area_name, area_prompt)
                
                # 在主线程中处理UI更新
                def update_ui():
                    try:
                        # show_bubble会自动处理表情解析和切换
                        # duration=None 会根据文字长度自动计算显示时长
                        self.show_bubble(response, duration=None)
                    finally:
                        # 解锁AI请求状态
                        self.is_waiting_ai_response = False
                
                self.root.after(0, update_ui)
                
            except Exception as e:
                logging.error(f"Touch reaction failed: {e}")
                
                def show_error():
                    self.show_bubble(f"触摸反应失败: {str(e)[:20]}...", duration=3000)  # 错误消息显示3秒
                    # 解锁AI请求状态
                    self.is_waiting_ai_response = False
                
                self.root.after(0, show_error)
        
        threading.Thread(target=async_touch_reaction, daemon=True).start()

    def show_context_menu(self, event):
        menu = Menu(self.root, tearoff=0)
        menu.add_command(label="喝一杯水", command=self.drink_water)
        menu.add_command(label="开启对话模式", command=self.start_manual_chat)
        menu.add_command(label="纪念日", command=self.open_anniversary_manager)
        menu.add_command(label="健康管理", command=self.open_health_manager)
        
        menu.add_separator()
        menu.add_command(label="角色管理", command=self.open_character_manager)
        menu.add_command(label="设置", command=self.open_settings)
        
        menu.add_separator()
        menu.add_command(label="退出", command=self.confirm_quit)
        menu.post(event.x_root, event.y_root)

    def start_manual_chat(self):
        # 对话框位置：立绘脚部重叠 5px
        input_width = 340 
        
        # 获取立绘底部在屏幕上的 Y 坐标
        char_screen_bottom_y = self.root.winfo_y() + self.root.winfo_height() - 20 # 默认 (假设底部预留20)
        
        # 尝试更精确获取
        try:
             items = self.canvas.find_withtag("character")
             if items:
                max_y = 0
                for item in items:
                    bbox = self.canvas.bbox(item)
                    if bbox and bbox[3] > max_y: max_y = bbox[3]
                if max_y > 0:
                    char_screen_bottom_y = self.root.winfo_y() + max_y
        except:
             pass
             
        # 目标 Y：重叠 5px -> 向上移动 5px
        target_y = int(char_screen_bottom_y - 5)
        
        # X 居中 (相对于窗口)
        x = self.root.winfo_x() + (self.root.winfo_width() - input_width) // 2
        
        InputBox(self.root, x, target_y, self.send_manual_chat, continuous_mode=True, config_manager=self.cm)
        
        # 如果没有历史记录，显示欢迎语
        if not self.cm.get_chat_history():
            self.show_bubble("来聊聊天吧！")

    def send_manual_chat(self, text):
        self.show_bubble("思考中...", duration=0)
        threading.Thread(target=self._async_ai_manual_chat, args=(text,), daemon=True).start()

    def confirm_quit(self):
        if self.is_closing: return
        self.is_closing = True
        self.show_bubble("告别准备中...", duration=0)
        threading.Thread(target=self._async_quit_process, daemon=True).start()

    def _async_quit_process(self):
        msg = self.ai_client.get_goodbye_message()
        self.root.after(0, lambda m=msg: self.show_bubble(m, duration=0))
        time.sleep(10)
        self.root.after(0, self._start_fade_out)

    def _start_fade_out(self):
        # 保存退出时间
        self.save_exit_time()
        
        alpha = 1.0
        def _fade():
            nonlocal alpha
            alpha -= 0.05
            if alpha <= 0:
                if self.tray_icon: self.tray_icon.stop()
                self.root.destroy()
                sys.exit()
            else:
                self.root.attributes('-alpha', alpha)
                self.root.after(50, _fade)
        _fade()
    
    def save_exit_time(self):
        """保存退出时间"""
        try:
            exit_time = datetime.now().isoformat()
            self.cm.set("last_exit_time", exit_time)
            logging.info(f"Exit time saved: {exit_time}")
        except Exception as e:
            logging.error(f"Failed to save exit time: {e}")


    def drink_water(self):
        current = self.cm.get("cups_drunk_today")
        target = self.cm.get("daily_target_cups")
        self.cm.set("cups_drunk_today", current + 1)
        self.schedule_next_reminder()
        self.show_bubble(f"喝水记录中...\n进度: {current+1}/{target}", duration=0)
        threading.Thread(target=self._async_ai_drink_feedback, daemon=True).start()

    def trigger_reminder(self, reminder_type="water"):
        """触发指定类型的提醒"""
        threading.Thread(target=self._async_ai_reminder, args=(reminder_type,), daemon=True).start()
        # 更新最后触发时间
        self.cm.update_reminder_last_triggered(reminder_type)

    def trigger_chat(self):
        # 锁定AI请求状态
        self.is_waiting_ai_response = True
        
        # 显示加载提示（直接调用create_bubble避免表情处理）
        self.create_bubble("...")
        
        threading.Thread(target=self._async_ai_chat, daemon=True).start()

    def _async_ai_reminder(self, reminder_type="water"):
        """异步获取提醒消息"""
        try:
            kwargs = {}
            
            # 为吃饭提醒添加时间段信息
            if reminder_type == "meal":
                hour = datetime.now().hour
                if 6 <= hour < 10:
                    kwargs["meal_time"] = "breakfast"
                elif 11 <= hour < 14:
                    kwargs["meal_time"] = "lunch"
                elif 17 <= hour < 20:
                    kwargs["meal_time"] = "dinner"
                else:
                    kwargs["meal_time"] = "meal time"
            
            msg = self.ai_client.get_reminder_message(reminder_type=reminder_type, **kwargs)
            self.root.after(0, lambda m=msg: self.show_bubble(m))
        except Exception as e:
            error_msg = f"提醒失败: {str(e)[:50]}"
            logging.error(f"AI reminder failed ({reminder_type}): {e}")
            self.root.after(0, lambda m=error_msg: self.show_bubble(m, duration=5000))

    def _async_ai_chat(self):
        # 尝试获取锁，如果忙则放弃（避免堆积）
        if not self.ai_lock.acquire(blocking=False):
            self.root.after(0, lambda: self.show_bubble("（正在思考其他事情...）", duration=2000))
            self.is_waiting_ai_response = False
            return

        try:
            msg = self.ai_client.get_chat_message()
            
            # 在主线程中处理UI更新
            def update_ui():
                try:
                    # show_bubble会自动处理表情解析和切换
                    self.show_bubble(msg)
                finally:
                    # 解锁AI请求状态
                    self.is_waiting_ai_response = False
            
            self.root.after(0, update_ui)
            
        except Exception as e:
            error_msg = f"闲聊失败: {str(e)[:50]}"
            logging.error(f"AI chat failed: {e}")
            
            def show_error():
                self.show_bubble(error_msg, duration=5000)
                # 解锁AI请求状态
                self.is_waiting_ai_response = False
            
            self.root.after(0, show_error)
        finally:
            self.ai_lock.release()
        
    def _async_ai_drink_feedback(self):
        if not self.ai_lock.acquire(blocking=False):
            return

        try:
            msg = self.ai_client.get_drink_feedback()
            self.root.after(0, lambda m=msg: self.show_bubble(m))
        except Exception as e:
            # 喝水反馈失败不显示错误，只记录日志
            logging.error(f"AI drink feedback failed: {e}")
        finally:
            self.ai_lock.release()

    def _async_ai_manual_chat(self, user_input):
        if not self.ai_lock.acquire(blocking=False):
             self.root.after(0, lambda: self.show_bubble("（正在思考其他事情...）", duration=2000))
             return

        try:
            msg = self.ai_client.chat_with_user(user_input)
            self.root.after(0, lambda m=msg: self.show_bubble(m))
        except Exception as e:
            error_msg = f"对话失败: {str(e)[:50]}\n请检查网络或API配置"
            logging.error(f"AI manual chat failed: {e}")
            self.root.after(0, lambda m=error_msg: self.show_bubble(m, duration=8000))
        finally:
            self.ai_lock.release()
        
    def _async_ai_welcome(self):
        if not self.ai_lock.acquire(blocking=True, timeout=10):
            return

        try:
            # 计算离线时长
            offline_info = self.calculate_offline_duration()
            
            # 传递离线信息给AI
            msg = self.ai_client.get_welcome_message(offline_info)
            self.root.after(0, lambda m=msg: self.show_bubble(m))
        except Exception as e:
            error_msg = f"欢迎消息加载失败\nAI服务可能暂时不可用"
            logging.error(f"AI welcome failed: {e}")
        finally:
            self.ai_lock.release()
    
    def perform_character_switch(self, target_char_id, current_char_info, target_char_info):
        """执行角色切换（带AI生成的告别和欢迎消息）"""
        # 第一步：当前角色说再见
        self.show_bubble("正在生成告别消息...", duration=0)
        threading.Thread(target=self._async_character_switch_goodbye, 
                        args=(target_char_id, current_char_info, target_char_info), 
                        daemon=True).start()
    
    def _async_character_switch_goodbye(self, target_char_id, current_char_info, target_char_info):
        """异步生成告别消息"""
        try:
            # 生成告别消息
            next_char_info = {
                "name": target_char_info.get("name", "未知"),
                "persona": target_char_info.get("persona", ""),
                "user_identity": target_char_info.get("user_identity", "")
            }
            goodbye_msg = self.ai_client.get_character_switch_goodbye(next_char_info)
            
            # 显示告别消息
            self.root.after(0, lambda m=goodbye_msg: self.show_bubble(m, duration=0))
            
            # 等待3秒让用户看到告别消息
            time.sleep(3)
            
            # 第二步：切换角色
            self.root.after(0, lambda: self._perform_switch_and_hello(target_char_id, current_char_info, target_char_info))
            
        except Exception as e:
            error_msg = f"告别消息生成失败: {str(e)[:50]}"
            logging.error(f"Character switch goodbye failed: {e}")
            self.root.after(0, lambda m=error_msg: self.show_bubble(m, duration=5000))
            # 即使失败也继续切换
            self.root.after(0, lambda: self._perform_switch_and_hello(target_char_id, current_char_info, target_char_info))
    
    def _perform_switch_and_hello(self, target_char_id, current_char_info, target_char_info):
        """执行切换并生成欢迎消息"""
        # 切换角色
        if not self.cm.switch_character(target_char_id):
            messagebox.showerror("错误", "角色切换失败")
            return
        
        # 先删除旧气泡并恢复窗口（重要！）
        self.canvas.delete("bubble_image")
        self.restore_window_height()
        
        # 强制更新窗口，确保高度恢复生效
        self.root.update_idletasks()
        
        # 重新加载AI客户端（使用新角色的配置）
        self.ai_client = AIClient(self.cm)
        
        # 重新加载资源和UI
        self.load_assets()
        self.setup_ui()
        
        # 重新绑定事件（关键！）
        self.bind_events()
        
        # 重新调度所有提醒
        self.schedule_all_reminders()
        
        # 等待一帧，确保UI完全渲染
        self.root.update_idletasks()
        
        # 显示加载消息
        self.show_bubble("正在生成欢迎消息...", duration=0)
        
        # 第三步：新角色打招呼
        threading.Thread(target=self._async_character_switch_hello, 
                        args=(current_char_info,), 
                        daemon=True).start()
    
    def _async_character_switch_hello(self, prev_char_info):
        """异步生成欢迎消息"""
        try:
            # 生成欢迎消息
            prev_char_info_dict = {
                "name": prev_char_info.get("name", "未知"),
                "persona": prev_char_info.get("persona", ""),
                "user_identity": prev_char_info.get("user_identity", "")
            }
            hello_msg = self.ai_client.get_character_switch_hello(prev_char_info_dict)
            
            # 显示欢迎消息
            self.root.after(0, lambda m=hello_msg: self.show_bubble(m))
            
        except Exception as e:
            error_msg = f"欢迎消息生成失败: {str(e)[:50]}"
            logging.error(f"Character switch hello failed: {e}")
            self.root.after(0, lambda m=error_msg: self.show_bubble(m, duration=5000))
            self.root.after(0, lambda m=error_msg: self.show_bubble(m, duration=5000))
    
    def calculate_offline_duration(self):
        """计算用户离线时长
        返回: dict with offline duration info
        """
        last_exit_time_str = self.cm.get("last_exit_time")
        
        if not last_exit_time_str:
            # 首次启动
            return {
                "is_first_time": True,
                "offline_seconds": 0,
                "offline_text": "这是第一次启动"
            }
        
        try:
            last_exit_time = datetime.fromisoformat(last_exit_time_str)
            now = datetime.now()
            offline_duration = now - last_exit_time
            offline_seconds = int(offline_duration.total_seconds())
            
            # 生成人类可读的时长描述
            if offline_seconds < 60:
                offline_text = f"{offline_seconds}秒"
            elif offline_seconds < 3600:
                minutes = offline_seconds // 60
                offline_text = f"{minutes}分钟"
            elif offline_seconds < 86400:
                hours = offline_seconds // 3600
                minutes = (offline_seconds % 3600) // 60
                if minutes > 0:
                    offline_text = f"{hours}小时{minutes}分钟"
                else:
                    offline_text = f"{hours}小时"
            else:
                days = offline_seconds // 86400
                hours = (offline_seconds % 86400) // 3600
                if hours > 0:
                    offline_text = f"{days}天{hours}小时"
                else:
                    offline_text = f"{days}天"
            
            logging.info(f"User was offline for {offline_text} (last exit: {last_exit_time_str})")
            
            return {
                "is_first_time": False,
                "offline_seconds": offline_seconds,
                "offline_text": offline_text,
                "last_exit_time": last_exit_time_str
            }
            
        except Exception as e:
            logging.error(f"Failed to calculate offline duration: {e}")
            return {
                "is_first_time": False,
                "offline_seconds": 0,
                "offline_text": "未知时长"
            }


    def calculate_interval(self):
        """计算喝水提醒间隔（根据今日工作时间和喝水目标）"""
        # 使用新的weekly_schedule
        work_start, work_end = self.cm.get_today_schedule()
        
        # 如果今天不是工作日或没有设置，返回-1（不提醒）
        if not work_start or not work_end:
            return -1
        
        target = self.cm.get("daily_target_cups")
        current = self.cm.get("cups_drunk_today")
        now = datetime.now()
        
        try:
            ws_h, ws_m = map(int, work_start.split(':'))
            we_h, we_m = map(int, work_end.split(':'))
            start_dt = now.replace(hour=ws_h, minute=ws_m, second=0, microsecond=0)
            end_dt = now.replace(hour=we_h, minute=we_m, second=0, microsecond=0)
            if start_dt > end_dt:
                if now >= start_dt: end_dt += timedelta(days=1)
                elif now <= end_dt: start_dt -= timedelta(days=1)
        except ValueError: 
            return 3600
            
        if now < start_dt: 
            return max(1, (start_dt - now).total_seconds())
        if now > end_dt: 
            return -1 
            
        remaining_cups = target - current
        if remaining_cups <= 0: 
            return -1 
            
        remaining_work_seconds = (end_dt - now).total_seconds()
        return max(remaining_work_seconds / remaining_cups, 900)

    def schedule_next_reminder(self):
        """调度喝水提醒"""
        interval = self.calculate_interval()
        if interval != -1:
            self.next_reminders["water"] = datetime.now() + timedelta(seconds=interval)
        else:
            self.next_reminders["water"] = None

    def schedule_next_chat(self):
        """调度随机闲聊"""
        if not self.cm.get("enable_random_chat"):
            self.next_chat_time = None
            return
        interval = self.cm.get("random_chat_interval")
        self.next_chat_time = datetime.now() + timedelta(minutes=int(interval) if interval else 60)
    
    def schedule_meal_reminders(self):
        """调度吃饭提醒（固定时间）"""
        config = self.cm.get_reminder_config("meal")
        if not config or not config.get("enabled"):
            self.next_reminders["meal"] = None
            return
        
        now = datetime.now()
        meal_times = config.get("times", [])
        
        # 找到下一个吃饭时间
        next_meal = None
        for time_str in meal_times:
            try:
                h, m = map(int, time_str.split(':'))
                meal_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if meal_dt > now:
                    if next_meal is None or meal_dt < next_meal:
                        next_meal = meal_dt
            except:
                continue
        
        # 如果今天没有了，设置为明天第一个
        if next_meal is None and meal_times:
            try:
                h, m = map(int, meal_times[0].split(':'))
                next_meal = (now + timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
            except:
                pass
        
        self.next_reminders["meal"] = next_meal
    
    def schedule_interval_reminder(self, reminder_type):
        """调度间隔型提醒（久坐、放松等）"""
        config = self.cm.get_reminder_config(reminder_type)
        if not config or not config.get("enabled"):
            self.next_reminders[reminder_type] = None
            return
        
        interval = config.get("interval", 60)  # 分钟
        
        # 检查上次触发时间
        last_triggered = config.get("last_triggered")
        if last_triggered:
            try:
                # 解析ISO格式的时间字符串
                last_dt = datetime.fromisoformat(last_triggered)
                next_time = last_dt + timedelta(minutes=interval)
                if next_time > datetime.now():
                    self.next_reminders[reminder_type] = next_time
                    return
            except:
                pass
        
        # 否则从现在开始计算
        self.next_reminders[reminder_type] = datetime.now() + timedelta(minutes=interval)
    
    def schedule_all_reminders(self):
        """初始化所有提醒"""
        self.schedule_next_reminder()  # 喝水
        self.schedule_meal_reminders()  # 吃饭
        self.schedule_interval_reminder("sitting")  # 久坐
        self.schedule_interval_reminder("relax")  # 放松
        self.schedule_medication_reminders()  # 吃药
        self.schedule_next_chat()  # 闲聊
    
    def schedule_medication_reminders(self):
        """调度吃药提醒（固定时间）"""
        medications = self.cm.get_medication_reminders()
        now = datetime.now()
        
        for med in medications:
            if not med.get("enabled", True):
                continue
            
            med_id = med.get("id")
            times = med.get("times", [])
            
            # 找到下一个吃药时间
            next_time = None
            for time_str in times:
                try:
                    h, m = map(int, time_str.split(':'))
                    med_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    if med_dt > now:
                        if next_time is None or med_dt < next_time:
                            next_time = med_dt
                except:
                    continue
            
            # 如果今天没有了，设置为明天第一个
            if next_time is None and times:
                try:
                    h, m = map(int, times[0].split(':'))
                    next_time = (now + timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
                except:
                    pass
            
            if next_time and med_id:
                self.next_reminders["medication"][med_id] = next_time

    def check_schedule(self):
        """检查所有提醒是否需要触发"""
        if not self.timer_running: 
            return
            
        self.cm.check_daily_reset()
        now = datetime.now()
        
        # 检查喝水提醒
        if self.next_reminders.get("water") and now >= self.next_reminders["water"]:
            self.trigger_reminder("water")
            self.schedule_next_reminder()
        
        # 检查吃饭提醒
        if self.next_reminders.get("meal") and now >= self.next_reminders["meal"]:
            self.trigger_reminder("meal")
            self.schedule_meal_reminders()
        
        # 检查久坐提醒
        if self.next_reminders.get("sitting") and now >= self.next_reminders["sitting"]:
            self.trigger_reminder("sitting")
            self.schedule_interval_reminder("sitting")
        
        # 检查放松提醒
        if self.next_reminders.get("relax") and now >= self.next_reminders["relax"]:
            self.trigger_reminder("relax")
            self.schedule_interval_reminder("relax")
        
        # 检查随机闲聊
        if self.next_chat_time and now >= self.next_chat_time:
            self.trigger_chat()
            self.schedule_next_chat()
        
        # 检查吃药提醒
        self._check_medication_reminders(now)
            
        # 检查自定义提醒
        self._check_custom_reminders(now)
        
        self.root.after(1000, self.check_schedule)
    
    def _check_medication_reminders(self, now):
        """检查吃药提醒"""
        medications = self.cm.get_medication_reminders()
        med_times = self.next_reminders.get("medication", {})
        
        triggered_meds = []
        for med in medications:
            if not med.get("enabled", True):
                continue
            
            med_id = med.get("id")
            if med_id in med_times and med_times[med_id] and now >= med_times[med_id]:
                # 触发提醒
                self.trigger_medication_reminder(med)
                triggered_meds.append(med_id)
        
        # 重新调度已触发的提醒
        if triggered_meds:
            self.schedule_medication_reminders()
    
    def trigger_medication_reminder(self, medication):
        """触发吃药提醒"""
        med_name = medication.get("name", "药品")
        threading.Thread(target=self._async_ai_medication_reminder, 
                        args=(med_name,), daemon=True).start()
    
    def _async_ai_medication_reminder(self, med_name):
        """异步获取吃药提醒消息"""
        try:
            msg = self.ai_client.get_reminder_message(reminder_type="medication", 
                                                     medication_name=med_name)
            self.root.after(0, lambda m=msg: self.show_bubble(m))
        except Exception as e:
            error_msg = f"吃药提醒失败: {str(e)[:50]}"
            logging.error(f"AI medication reminder failed: {e}")
            self.root.after(0, lambda m=error_msg: self.show_bubble(m, duration=5000))

    def _check_custom_reminders(self, now):
        reminders = self.cm.get("reminders")
        if not reminders or "custom" not in reminders:
            return
            
        custom_list = reminders.get("custom", [])
        if not custom_list:
            return
            
        modified = False
        new_list = []
        
        for r in custom_list:
            should_keep = True
            try:
                if "next_trigger_time" in r:
                    trigger_time = datetime.fromisoformat(r["next_trigger_time"])
                    if now >= trigger_time:
                        # 触发提醒
                        self.trigger_custom_reminder(r)
                        
                        # 更新计数
                        r["remaining_count"] -= 1
                        modified = True
                        
                        if r["remaining_count"] > 0:
                            # 计算下次时间
                            next_time = datetime.now() + timedelta(minutes=int(r["interval"]))
                            r["next_trigger_time"] = next_time.isoformat()
                        else:
                            should_keep = False
            except Exception as e:
                logging.error(f"Error checking custom reminder: {e}")
            
            if should_keep:
                new_list.append(r)
        
        if modified:
            reminders["custom"] = new_list
            self.cm.set("reminders", reminders)
            # 如果有提醒管理器打开，可能需要刷新它（这里简化处理，不做实时刷新）

    def open_anniversary_manager(self):
        AnniversaryManagerWindow(self.root, self.cm)
    
    def open_character_manager(self):
        """打开角色管理窗口"""
        CharacterManagerWindow(self.root, self.cm, self)
    
    def open_health_manager(self):
        HealthManagerWindow(self.root, self.cm, self)
    
    def quick_record_period(self):
        """快捷记录生理期开始"""
        self.cm.record_period_start()
        self.show_bubble("已记录生理期开始日期", duration=3000)
        # 可选：让AI作出响应
        threading.Thread(target=self._async_period_recorded, daemon=True).start()
    
    def _async_period_recorded(self):
        """生理期记录后的AI响应（可选）"""
        try:
            # 这里可以让AI知道用户记录了生理期
            # 暂时使用简单的欢迎消息作为响应
            pass
        except Exception as e:
            logging.error(f"Period record notification failed: {e}")
        
    def trigger_custom_reminder(self, reminder_data):
        content = reminder_data.get("content", "")
        remaining = reminder_data.get("remaining_count", 0) - 1 # 显示剩余次数（不含本次）
        if remaining < 0: remaining = 0
        
        threading.Thread(target=self._async_ai_reminder, args=("custom",), 
                        kwargs={"custom_message": content, "remaining_count": remaining}, 
                        daemon=True).start()

    def trigger_easter_egg(self):
        """触发连续点击彩蛋"""
        self.show_bubble("好痒！别挠了！>_<", duration=2000)
        # 尝试切换到害羞或惊讶表情
        for expr in ["shy", "surprised", "happy"]:
            if expr in self.expressions:
                self.set_expression(expr)
                break

    def check_daily_briefing(self):
        """检查并触发每日早报"""
        today = datetime.now().strftime("%Y-%m-%d")
        last_date = self.cm.get("last_daily_briefing_date")
        
        # 如果是新的一天，且现在是早上5点到12点之间
        if last_date != today:
            hour = datetime.now().hour
            if 5 <= hour < 12:
                # 触发早报
                threading.Thread(target=self._async_daily_briefing, daemon=True).start()
                # 更新最后播报日期
                self.cm.set("last_daily_briefing_date", today)

    def _async_daily_briefing(self):
        try:
            now = datetime.now()
            date_str = now.strftime("%Y年%m月%d日")
            weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            weekday_str = weekdays[now.weekday()]
            
            # 获取天气信息
            city = self.cm.get("weather_city")
            weather_key = self.cm.get("weather_api_key")
            
            from utils import get_weather_info
            
            if city:
                weather_info = get_weather_info(city, weather_key)
            else:
                # 尝试自动定位 (IP)
                weather_info = get_weather_info(None, None)
            
            # 使用锁防止与欢迎消息冲突
            # 等待一小会儿，让欢迎消息先显示完
            time.sleep(5)
            
            msg = self.ai_client.get_daily_briefing_message(date_str, weekday_str, weather_info)
            self.root.after(0, lambda: self.show_bubble(msg))
        except Exception as e:
            logging.error(f"Daily briefing failed: {e}")

    def open_settings(self):
        SettingsWindow(self.root, self.cm, self.ai_client, self.update_after_settings)

    def update_after_settings(self):
        """设置更新后重新调度所有提醒和重新加载资源"""
        self.schedule_all_reminders()
        # 重新加载表情立绘
        self.load_assets()
        self.setup_ui()
        # 重新绑定事件（重要！）
        self.bind_events()
        self.show_bubble("设置已更新！字体将在下次显示气泡时生效。")

class ExpressionDialog(ctk.CTkToplevel):
    def __init__(self, parent, entry_data, callback):
        super().__init__(parent)
        self.entry_data = entry_data
        self.callback = callback
        
        self.title("编辑表情映射")
        self.geometry("450x300")
        
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - 450) // 2
            y = (sh - 300) // 2
            self.geometry(f"+{x}+{y}")
        except:
            pass
            
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        
        self.setup_ui()
        
    def setup_ui(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 关键词
        ctk.CTkLabel(container, text="表情关键词", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        ctk.CTkLabel(container, text="AI回复中的表情标签，如：生气、宠溺、无语等", font=("Microsoft YaHei UI", 10), text_color="gray").pack(anchor="w", pady=(0, 5))
        self.entry_keyword = ctk.CTkEntry(container, placeholder_text="例如：宠溺")
        self.entry_keyword.pack(fill="x", pady=(5, 15))
        if self.entry_data and "keyword" in self.entry_data:
            self.entry_keyword.insert(0, self.entry_data["keyword"])
            
        # 文件路径
        ctk.CTkLabel(container, text="立绘文件路径", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        ctk.CTkLabel(container, text="相对或绝对路径，如：expressions/smirk.png", font=("Microsoft YaHei UI", 10), text_color="gray").pack(anchor="w", pady=(0, 5))
        
        path_frame = ctk.CTkFrame(container, fg_color="transparent")
        path_frame.pack(fill="x", pady=(5, 20))
        
        self.entry_path = ctk.CTkEntry(path_frame, placeholder_text="例如：expressions/smirk.png")
        self.entry_path.pack(side="left", fill="x", expand=True, padx=(0, 5))
        if self.entry_data and "path" in self.entry_data:
            self.entry_path.insert(0, self.entry_data["path"])
        
        ctk.CTkButton(path_frame, text="浏览", width=60, fg_color="#7EA0B7", command=self.browse_file).pack(side="right")
            
        # 按钮
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x")
        ctk.CTkButton(btn_frame, text="取消", fg_color="transparent", border_width=1, text_color="gray", command=self.destroy).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(btn_frame, text="保存", fg_color="#7EA0B7", command=self.save).pack(side="right", expand=True, padx=5)

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="选择表情立绘",
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.webp")]
        )
        if file_path:
            self.entry_path.delete(0, 'end')
            self.entry_path.insert(0, file_path)

    def save(self):
        keyword = self.entry_keyword.get().strip()
        path = self.entry_path.get().strip()
        
        if not keyword:
            messagebox.showwarning("提示", "请输入表情关键词")
            return
        
        if not path:
            messagebox.showwarning("提示", "请输入立绘文件路径")
            return
            
        data = {
            "keyword": keyword,
            "path": path
        }
        
        self.callback(data)
        self.destroy()

class LorebookDialog(ctk.CTkToplevel):
    def __init__(self, parent, entry_data, callback):
        super().__init__(parent)
        self.entry_data = entry_data
        self.callback = callback
        
        self.title("编辑世界书条目")
        self.geometry("450x400")
        
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - 450) // 2
            y = (sh - 400) // 2
            self.geometry(f"+{x}+{y}")
        except:
            pass
            
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        
        self.setup_ui()
        
    def setup_ui(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 触发类型
        ctk.CTkLabel(container, text="触发类型", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        self.type_var = ctk.StringVar(value=self.entry_data.get("type", "keyword") if self.entry_data else "keyword")
        
        type_frame = ctk.CTkFrame(container, fg_color="transparent")
        type_frame.pack(fill="x", pady=(5, 15))
        
        ctk.CTkRadioButton(type_frame, text="关键词触发", variable=self.type_var, value="keyword", command=self.on_type_change).pack(side="left", padx=(0, 20))
        ctk.CTkRadioButton(type_frame, text="常驻 (总是发送)", variable=self.type_var, value="always", command=self.on_type_change).pack(side="left")
        
        # 关键词
        self.lbl_keyword = ctk.CTkLabel(container, text="触发关键词 (多个词用逗号分隔)", font=("Microsoft YaHei UI", 12, "bold"))
        self.lbl_keyword.pack(anchor="w")
        
        self.entry_keywords = ctk.CTkEntry(container, placeholder_text="例如：魔法, 城堡, 或者是某个人名")
        self.entry_keywords.pack(fill="x", pady=(5, 15))
        if self.entry_data and "keywords" in self.entry_data:
            self.entry_keywords.insert(0, self.entry_data["keywords"])
            
        # 内容
        ctk.CTkLabel(container, text="背景知识内容", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        self.txt_content = ctk.CTkTextbox(container, height=120)
        self.txt_content.pack(fill="x", pady=(5, 20))
        if self.entry_data and "content" in self.entry_data:
            self.txt_content.insert("1.0", self.entry_data["content"])
            
        # 按钮
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x")
        ctk.CTkButton(btn_frame, text="取消", fg_color="transparent", border_width=1, text_color="gray", command=self.destroy).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(btn_frame, text="保存", fg_color="#7EA0B7", command=self.save).pack(side="right", expand=True, padx=5)

        self.on_type_change()

    def on_type_change(self):
        if self.type_var.get() == "always":
            self.entry_keywords.configure(state="disabled", fg_color="#E0E0E0")
        else:
            self.entry_keywords.configure(state="normal", fg_color=["#F9F9FA", "#343638"]) # 根据主题自动适配

    def save(self):
        content = self.txt_content.get("1.0", "end").strip()
        if not content:
            messagebox.showwarning("提示", "请输入内容")
            return
            
        keywords = self.entry_keywords.get().strip()
        entry_type = self.type_var.get()
        
        if entry_type == "keyword" and not keywords:
            messagebox.showwarning("提示", "关键词触发模式下，必须输入关键词")
            return
            
        data = {
            "id": self.entry_data.get("id", str(uuid.uuid4())) if self.entry_data else str(uuid.uuid4()),
            "type": entry_type,
            "keywords": keywords,
            "content": content
        }
        
        self.callback(data)
        self.destroy()

class TouchAreaDialog(ctk.CTkToplevel):
    """触摸区域信息编辑对话框"""
    def __init__(self, parent, area_data, callback):
        super().__init__(parent)
        self.area_data = area_data
        self.callback = callback
        
        self.title("编辑触摸区域")
        self.geometry("450x350")
        
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - 450) // 2
            y = (sh - 350) // 2
            self.geometry(f"+{x}+{y}")
        except:
            pass
            
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        
        self.setup_ui()
        
    def setup_ui(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 区域名称
        ctk.CTkLabel(container, text="区域名称", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        ctk.CTkLabel(container, text="如：头部、脸颊、手、肩膀等", font=("Microsoft YaHei UI", 10), text_color="gray").pack(anchor="w", pady=(0, 5))
        self.entry_name = ctk.CTkEntry(container, placeholder_text="例如：头部")
        self.entry_name.pack(fill="x", pady=(5, 15))
        if self.area_data and "name" in self.area_data:
            self.entry_name.insert(0, self.area_data["name"])
            
        # 触摸提示词
        ctk.CTkLabel(container, text="触摸提示词", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        ctk.CTkLabel(container, text="发送给AI的额外提示，描述这次触摸的情境", font=("Microsoft YaHei UI", 10), text_color="gray").pack(anchor="w", pady=(0, 5))
        
        self.txt_prompt = ctk.CTkTextbox(container, height=100, border_width=0, fg_color="#F2F2F7", corner_radius=10)
        self.txt_prompt.pack(fill="both", expand=True, pady=(5, 20))
        if self.area_data and "prompt" in self.area_data:
            self.txt_prompt.insert("1.0", self.area_data["prompt"])
        else:
            self.txt_prompt.insert("1.0", "用户温柔地触摸了你的{area_name}，请做出自然的反应。")
            
        # 按钮
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x")
        ctk.CTkButton(btn_frame, text="取消", fg_color="transparent", border_width=1, text_color="gray", command=self.destroy).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(btn_frame, text="保存", fg_color="#7EA0B7", command=self.save).pack(side="right", expand=True, padx=5)

    def save(self):
        name = self.entry_name.get().strip()
        prompt = self.txt_prompt.get("1.0", "end-1c").strip()
        
        if not name:
            messagebox.showwarning("提示", "请输入区域名称")
            return
            
        data = {
            "name": name,
            "prompt": prompt
        }
        
        # 如果是编辑模式，保留原有的位置和尺寸信息
        if self.area_data:
            if "id" in self.area_data:
                data["id"] = self.area_data["id"]
            if "x" in self.area_data:
                data["x"] = self.area_data["x"]
            if "y" in self.area_data:
                data["y"] = self.area_data["y"]
            if "width" in self.area_data:
                data["width"] = self.area_data["width"]
            if "height" in self.area_data:
                data["height"] = self.area_data["height"]
        
        self.callback(data)
        self.destroy()

class TouchAreaEditorWindow(ctk.CTkToplevel):
    """触摸区域可视化编辑器"""
    def __init__(self, parent, config_manager, callback):
        super().__init__(parent)
        self.cm = config_manager
        self.callback = callback
        
        self.title("触摸区域编辑器")
        self.geometry("950x780")  # 容纳 600x500 的画布 + 右侧列表 + 边距
        
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - 800) // 2
            y = (sh - 700) // 2
            self.geometry(f"+{x}+{y}")
        except:
            pass
            
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        
        # 状态变量
        self.drawing = False
        self.start_x = 0
        self.start_y = 0
        self.current_rect = None
        self.areas = []  # 存储所有区域
        self.selected_area_index = None
        
        # 加载现有配置
        touch_config = self.cm.get("touch_areas") or {"enabled": True, "areas": []}
        self.areas = touch_config.get("areas", []).copy()
        
        self.setup_ui()
        # draw_all_areas 会在 load_character_image 之后调用
        
    def setup_ui(self):
        # 主容器
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 顶部说明
        info_frame = ctk.CTkFrame(main_container, fg_color="#E8F4F8", corner_radius=10)
        info_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(info_frame, text="使用说明", font=("Microsoft YaHei UI", 13, "bold"), text_color="#333333").pack(anchor="w", padx=15, pady=(10, 5))
        ctk.CTkLabel(info_frame, text="• 在立绘上拖动鼠标绘制矩形框来定义触摸区域", font=("Microsoft YaHei UI", 11), text_color="gray", anchor="w").pack(anchor="w", padx=15)
        ctk.CTkLabel(info_frame, text="• 点击右侧区域列表可以编辑或删除", font=("Microsoft YaHei UI", 11), text_color="gray", anchor="w").pack(anchor="w", padx=15, pady=(0, 10))
        
        # 中间内容区域（左右分栏）
        content_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)
        
        # 左侧：画布区域
        left_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        ctk.CTkLabel(left_frame, text="立绘预览", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        
        canvas_frame = ctk.CTkFrame(left_frame, fg_color="#F2F2F7", corner_radius=10)
        canvas_frame.pack(fill="both", expand=True)
        
        # 创建画布 - 使用与主窗口相同的尺寸 600x500
        self.canvas = tk.Canvas(canvas_frame, width=600, height=500, bg="white", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(padx=10, pady=10)
        
        # 绑定鼠标事件
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        
        # 延迟加载立绘图片，确保画布完成布局
        self.after(100, self.load_character_image)
        
        # 右侧：区域列表
        right_frame = ctk.CTkFrame(content_frame, fg_color="transparent", width=250)
        right_frame.pack(side="right", fill="both")
        right_frame.pack_propagate(False)
        
        ctk.CTkLabel(right_frame, text="触摸区域列表", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        
        # 区域列表滚动框
        self.area_list_frame = ctk.CTkScrollableFrame(right_frame, fg_color="#F2F2F7", corner_radius=10)
        self.area_list_frame.pack(fill="both", expand=True)
        
        self.refresh_area_list()
        
        # 底部按钮
        btn_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(15, 0))
        
        ctk.CTkButton(btn_frame, text="取消", fg_color="transparent", border_width=1, text_color="gray", 
                     command=self.destroy, height=40, corner_radius=20).pack(side="left", expand=True, padx=(0, 5))
        ctk.CTkButton(btn_frame, text="保存所有区域", fg_color="#7EA0B7", hover_color="#6C8EA4",
                     command=self.save_all, height=40, corner_radius=20).pack(side="right", expand=True, padx=(5, 0))
    
    def load_character_image(self):
        """加载立绘图片到画布"""
        # 获取表情配置中的默认立绘
        expressions_config = self.cm.get("expressions") or {"default": ""}
        default_img = expressions_config.get("default", "")
        
        # 如果没有配置 default，使用当前角色的 avatar
        if not default_img:
            current_char = self.cm.get_current_character()
            if current_char:
                default_img = current_char.get("avatar", "character.png")
            else:
                default_img = "character.png"
        
        # 尝试加载图片
        img_path = default_img
        if not os.path.exists(img_path):
            img_path = resource_path(default_img)
        
        if not os.path.exists(img_path):
            # 如果找不到图片，显示提示
            self.canvas.create_text(250, 250, text="未找到立绘图片\n请先设置默认立绘", 
                                   fill="gray", font=("Microsoft YaHei UI", 14), justify=tk.CENTER)
            self.character_image = None
            return
        
        try:
            pil_image = PILImage.open(img_path)
            
            # 确保图像为RGBA模式
            if pil_image.mode != 'RGBA':
                pil_image = pil_image.convert('RGBA')
            
            # 保存原始尺寸
            original_width = pil_image.width
            original_height = pil_image.height
            
            # ===== 使用与主窗口完全相同的缩放逻辑 =====
            # 主窗口的立绘高度限制为 400px
            if pil_image.height > 400:
                ratio = 400 / pil_image.height
                new_width = int(pil_image.width * ratio)
                new_height = 400
                pil_image = pil_image.resize((new_width, new_height), PILImage.Resampling.LANCZOS)
            else:
                new_width = pil_image.width
                new_height = pil_image.height
            
            # 保存缩放后的尺寸
            self.img_display_width = new_width
            self.img_display_height = new_height
            
            # 转换为PhotoImage
            self.character_image = ImageTk.PhotoImage(pil_image)
            
            # ===== 使用与主窗口完全相同的显示位置 =====
            # 主窗口: self.canvas.create_image(370, 480, image=current_photo, anchor=tk.S)
            x = 370
            y = 480
            
            self.canvas.create_image(x, y, image=self.character_image, anchor=tk.S, tags="character")
            
            # 记录图片的边界（用于坐标转换）
            # 由于anchor=S（底部对齐），所以立绘的左上角位置是：
            self.img_left = x - new_width // 2
            self.img_top = y - new_height
            
            logging.info(f"Editor character loaded: size={new_width}x{new_height}, position=({x},{y}), bbox=({self.img_left},{self.img_top})")
            
            # 在画布上绘制参考线，显示立绘边界（调试用）
            # self.canvas.create_rectangle(self.img_left, self.img_top, self.img_left + new_width, self.img_top + new_height, 
            #                              outline="red", width=2, dash=(5,5), tags="debug_boundary")
            
            # 立绘加载完成后，绘制已配置的触摸区域
            self.draw_all_areas()
            
        except Exception as e:
            logging.error(f"Failed to load character image: {e}")
            self.canvas.create_text(250, 250, text=f"加载立绘失败\n{str(e)}", 
                                   fill="red", font=("Microsoft YaHei UI", 12), justify=tk.CENTER)
            self.character_image = None
    
    def on_mouse_press(self, event):
        """鼠标按下"""
        self.drawing = True
        self.start_x = event.x
        self.start_y = event.y
        
    def on_mouse_drag(self, event):
        """鼠标拖动"""
        if not self.drawing:
            return
        
        # 删除旧的临时矩形
        if self.current_rect:
            self.canvas.delete(self.current_rect)
        
        # 绘制新的矩形
        self.current_rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, event.x, event.y,
            outline="#FF6B6B", width=2, dash=(5, 5), tags="temp_rect"
        )
    
    def on_mouse_release(self, event):
        """鼠标释放"""
        if not self.drawing:
            return
        
        self.drawing = False
        
        # 删除临时矩形
        if self.current_rect:
            self.canvas.delete(self.current_rect)
            self.current_rect = None
        
        # 计算矩形坐标
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        width = x2 - x1
        height = y2 - y1
        
        # 忽略太小的矩形
        if width < 10 or height < 10:
            return
        
        # 转换为相对于立绘的坐标
        if hasattr(self, 'img_left') and hasattr(self, 'img_top'):
            relative_x = x1 - self.img_left
            relative_y = y1 - self.img_top
        else:
            relative_x = x1
            relative_y = y1
        
        # 打开对话框输入区域信息
        area_data = {
            "x": int(relative_x),
            "y": int(relative_y),
            "width": int(width),
            "height": int(height),
            "id": str(uuid.uuid4())
        }
        
        TouchAreaDialog(self, area_data, lambda data: self.add_area(data))
    
    def add_area(self, area_data):
        """添加新区域"""
        self.areas.append(area_data)
        self.draw_all_areas()
        self.refresh_area_list()
    
    def draw_all_areas(self):
        """绘制所有区域"""
        # 删除所有旧的区域矩形
        self.canvas.delete("area_rect")
        self.canvas.delete("area_label")
        
        # 绘制每个区域
        for i, area in enumerate(self.areas):
            x = area.get("x", 0)
            y = area.get("y", 0)
            width = area.get("width", 0)
            height = area.get("height", 0)
            
            # 转换为画布坐标
            if hasattr(self, 'img_left') and hasattr(self, 'img_top'):
                canvas_x = x + self.img_left
                canvas_y = y + self.img_top
            else:
                canvas_x = x
                canvas_y = y
            
            # 绘制矩形
            color = "#7EA0B7"
            rect_id = self.canvas.create_rectangle(
                canvas_x, canvas_y, canvas_x + width, canvas_y + height,
                outline=color, width=2, tags="area_rect"
            )
            
            # 绘制标签
            name = area.get("name", f"区域{i+1}")
            label_id = self.canvas.create_text(
                canvas_x + 5, canvas_y + 5,
                text=name, fill=color, anchor=tk.NW,
                font=("Microsoft YaHei UI", 10, "bold"),
                tags="area_label"
            )
    
    def refresh_area_list(self):
        """刷新区域列表"""
        # 清空列表
        for widget in self.area_list_frame.winfo_children():
            widget.destroy()
        
        if not self.areas:
            empty_label = ctk.CTkLabel(self.area_list_frame, text="暂无触摸区域\n在左侧立绘上拖动鼠标创建", 
                                       text_color="gray", font=("Microsoft YaHei UI", 11))
            empty_label.pack(pady=50)
            return
        
        # 显示每个区域
        for i, area in enumerate(self.areas):
            self.create_area_item(i, area)
    
    def create_area_item(self, index, area):
        """创建区域列表项"""
        item = ctk.CTkFrame(self.area_list_frame, fg_color="white", corner_radius=5)
        item.pack(fill="x", pady=2, padx=2)
        
        info_frame = ctk.CTkFrame(item, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=10, pady=8)
        
        name = area.get("name", f"区域{index+1}")
        ctk.CTkLabel(info_frame, text=name, font=("Microsoft YaHei UI", 13, "bold"), 
                    text_color="#333333", anchor="w").pack(fill="x")
        
        pos_text = f"位置: ({area.get('x', 0)}, {area.get('y', 0)})  大小: {area.get('width', 0)}×{area.get('height', 0)}"
        ctk.CTkLabel(info_frame, text=pos_text, font=("Microsoft YaHei UI", 10), 
                    text_color="gray", anchor="w").pack(fill="x")
        
        # 按钮
        btn_frame = ctk.CTkFrame(item, fg_color="transparent")
        btn_frame.pack(side="right", padx=5)
        
        ctk.CTkButton(btn_frame, text="✎", width=30, height=30, fg_color="#7EA0B7", 
                     hover_color="#6C8EA4", command=lambda: self.edit_area(index)).pack(side="left", padx=2)
        ctk.CTkButton(btn_frame, text="×", width=30, height=30, fg_color="#FF6B6B", 
                     hover_color="#FF5252", command=lambda: self.delete_area(index)).pack(side="left", padx=2)
    
    def edit_area(self, index):
        """编辑区域"""
        if 0 <= index < len(self.areas):
            area_data = self.areas[index].copy()
            
            def update_area(new_data):
                self.areas[index] = new_data
                self.draw_all_areas()
                self.refresh_area_list()
            
            TouchAreaDialog(self, area_data, update_area)
    
    def delete_area(self, index):
        """删除区域"""
        if 0 <= index < len(self.areas):
            name = self.areas[index].get("name", f"区域{index+1}")
            if messagebox.askyesno("确认删除", f"确定要删除区域 '{name}' 吗？"):
                self.areas.pop(index)
                self.draw_all_areas()
                self.refresh_area_list()
    
    def save_all(self):
        """保存所有区域"""
        touch_config = {
            "enabled": True,
            "areas": self.areas
        }
        self.cm.set("touch_areas", touch_config)
        
        messagebox.showinfo("保存成功", f"已保存 {len(self.areas)} 个触摸区域")
        
        if self.callback:
            self.callback()
        
        self.destroy()

class AddMedicationDialog(ctk.CTkToplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.title("添加吃药提醒")
        self.geometry("400x350")
        
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - 400) // 2
            y = (sh - 350) // 2
            self.geometry(f"+{x}+{y}")
        except:
            pass
            
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        
        self.setup_ui()
        
    def setup_ui(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 药名
        ctk.CTkLabel(container, text="药品名称", font=("Microsoft YaHei UI", 12), text_color="gray").pack(anchor="w")
        self.entry_name = ctk.CTkEntry(container, placeholder_text="例如：维生素C、感冒药等")
        self.entry_name.pack(fill="x", pady=(5, 15))
        
        # 时间
        ctk.CTkLabel(container, text="提醒时间（逗号分隔）", font=("Microsoft YaHei UI", 12), text_color="gray").pack(anchor="w")
        self.entry_times = ctk.CTkEntry(container, placeholder_text="08:00, 20:00")
        self.entry_times.pack(fill="x", pady=(5, 15))
        
        # 备注
        ctk.CTkLabel(container, text="备注（可选）", font=("Microsoft YaHei UI", 12), text_color="gray").pack(anchor="w")
        self.entry_notes = ctk.CTkEntry(container, placeholder_text="饭后服用、注意事项等")
        self.entry_notes.pack(fill="x", pady=(5, 20))
        
        # 按钮
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=10)
        
        ctk.CTkButton(btn_frame, text="取消", fg_color="transparent", border_width=1, text_color="gray", command=self.destroy).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(btn_frame, text="确定", fg_color="#7EA0B7", command=self.save).pack(side="right", expand=True, padx=5)
        
    def save(self):
        name = self.entry_name.get().strip()
        if not name:
            messagebox.showwarning("提示", "请输入药品名称")
            return
        
        times_str = self.entry_times.get().strip()
        if not times_str:
            messagebox.showwarning("提示", "请输入提醒时间")
            return
        
        # 解析时间列表
        times = [t.strip() for t in times_str.replace("，", ",").split(",") if t.strip()]
        if not times:
            messagebox.showwarning("提示", "请输入有效的时间格式")
            return
        
        # 验证时间格式
        for t in times:
            try:
                h, m = t.split(':')
                h, m = int(h), int(m)
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    raise ValueError
            except:
                messagebox.showerror("错误", f"时间格式错误：{t}，请使用 HH:MM 格式")
                return
        
        notes = self.entry_notes.get().strip()
        
        self.callback(name, times, notes)
        self.destroy()

class AddAnniversaryDialog(ctk.CTkToplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.title("新建纪念日")
        self.geometry("400x380")
        
        # 居中
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - 400) // 2
            y = (sh - 380) // 2
            self.geometry(f"+{x}+{y}")
        except:
            pass
            
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        
        self.setup_ui()
        
    def setup_ui(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 标题
        ctk.CTkLabel(container, text="纪念日标题", font=("Microsoft YaHei UI", 12), text_color="gray").pack(anchor="w")
        self.entry_title = ctk.CTkEntry(container, placeholder_text="例如：小明生日、生理期等")
        self.entry_title.pack(fill="x", pady=(5, 15))
        
        # 类型选择
        ctk.CTkLabel(container, text="类型", font=("Microsoft YaHei UI", 12), text_color="gray").pack(anchor="w")
        self.type_var = ctk.StringVar(value="birthday")
        type_frame = ctk.CTkFrame(container, fg_color="transparent")
        type_frame.pack(fill="x", pady=(5, 15))
        ctk.CTkRadioButton(type_frame, text="生日", variable=self.type_var, value="birthday").pack(side="left", padx=(0, 10))
        ctk.CTkRadioButton(type_frame, text="生理期", variable=self.type_var, value="period").pack(side="left", padx=(0, 10))
        ctk.CTkRadioButton(type_frame, text="其他", variable=self.type_var, value="custom").pack(side="left")
        
        # 日期
        ctk.CTkLabel(container, text="日期 (MM-DD)", font=("Microsoft YaHei UI", 12), text_color="gray").pack(anchor="w")
        self.entry_date = ctk.CTkEntry(container, placeholder_text="01-15")
        self.entry_date.pack(fill="x", pady=(5, 15))
        
        # 备注
        ctk.CTkLabel(container, text="备注（可选）", font=("Microsoft YaHei UI", 12), text_color="gray").pack(anchor="w")
        self.entry_notes = ctk.CTkEntry(container, placeholder_text="额外提示信息")
        self.entry_notes.pack(fill="x", pady=(5, 20))
        
        # 按钮
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=10)
        
        ctk.CTkButton(btn_frame, text="取消", fg_color="transparent", border_width=1, text_color="gray", command=self.destroy).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(btn_frame, text="确定", fg_color="#7EA0B7", command=self.save).pack(side="right", expand=True, padx=5)
        
    def save(self):
        title = self.entry_title.get().strip()
        if not title:
            messagebox.showwarning("提示", "请输入纪念日标题")
            return
        
        date_str = self.entry_date.get().strip()
        if not date_str:
            messagebox.showwarning("提示", "请输入日期")
            return
        
        # 验证日期格式
        try:
            month, day = date_str.split('-')
            month, day = int(month), int(day)
            if not (1 <= month <= 12 and 1 <= day <= 31):
                raise ValueError
            date_str = f"{month:02d}-{day:02d}"
        except:
            messagebox.showerror("错误", "日期格式错误，请使用 MM-DD 格式，如：01-15")
            return
        
        anniversary_type = self.type_var.get()
        notes = self.entry_notes.get().strip()
        
        self.callback(title, date_str, anniversary_type, notes)
        self.destroy()

class AddReminderDialog(ctk.CTkToplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.title("新建提醒")
        self.geometry("400x350")
        
        # 居中
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - 400) // 2
            y = (sh - 350) // 2
            self.geometry(f"+{x}+{y}")
        except:
            pass
            
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        
        self.setup_ui()
        
    def setup_ui(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 内容
        ctk.CTkLabel(container, text="提醒内容", font=("Microsoft YaHei UI", 12), text_color="gray").pack(anchor="w")
        self.entry_content = ctk.CTkEntry(container, placeholder_text="例如：休息眼睛、喝水、背单词...")
        self.entry_content.pack(fill="x", pady=(5, 15))
        
        # 周期
        ctk.CTkLabel(container, text="提醒周期 (分钟)", font=("Microsoft YaHei UI", 12), text_color="gray").pack(anchor="w")
        self.entry_interval = ctk.CTkEntry(container, placeholder_text="25")
        self.entry_interval.insert(0, "25")
        self.entry_interval.pack(fill="x", pady=(5, 15))
        
        # 次数
        ctk.CTkLabel(container, text="重复次数", font=("Microsoft YaHei UI", 12), text_color="gray").pack(anchor="w")
        self.entry_count = ctk.CTkEntry(container, placeholder_text="3")
        self.entry_count.insert(0, "3")
        self.entry_count.pack(fill="x", pady=(5, 20))
        
        # 按钮
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=10)
        
        ctk.CTkButton(btn_frame, text="取消", fg_color="transparent", border_width=1, text_color="gray", command=self.destroy).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(btn_frame, text="确定", fg_color="#7EA0B7", command=self.save).pack(side="right", expand=True, padx=5)
        
    def save(self):
        content = self.entry_content.get().strip()
        if not content:
            messagebox.showwarning("提示", "请输入提醒内容")
            return
            
        try:
            interval = int(self.entry_interval.get())
            count = int(self.entry_count.get())
            if interval <= 0 or count <= 0:
                raise ValueError
        except:
            messagebox.showerror("错误", "周期和次数必须为正整数")
            return
            
        self.callback(content, interval, count)
        self.destroy()

class HealthManagerWindow(ctk.CTkToplevel):
    def __init__(self, parent, config_manager, app_instance):
        super().__init__(parent)
        self.cm = config_manager
        self.app = app_instance  # 主窗口实例，用于触发快捷记录
        self.title("健康管理")
        self.geometry("550x700")
        
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - 550) // 2
            y = (sh - 700) // 2
            self.geometry(f"+{x}+{y}")
        except:
            pass

        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))

        self.setup_ui()
        
    def setup_ui(self):
        # 标签页
        self.tabview = ctk.CTkTabview(self, height=600, corner_radius=15)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=20)
        
        self.tab_period = self.tabview.add("生理期")
        self.tab_medication = self.tabview.add("吃药提醒")
        
        self.setup_period_tab(self.tab_period)
        self.setup_medication_tab(self.tab_medication)
    
    def setup_period_tab(self, parent):
        container = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 提示信息
        info_frame = ctk.CTkFrame(container, fg_color="#FFF9E6", corner_radius=10)
        info_frame.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(info_frame, text="提示：生理期数据仅存储在本地，打包时不会包含", 
                    font=("Microsoft YaHei UI", 11), text_color="#8B7500").pack(pady=10, padx=10)
        
        # 启用开关
        health = self.cm.get("health") or {}
        period_tracker = health.get("period_tracker", {})
        
        self.period_enabled = ctk.BooleanVar(value=period_tracker.get("enabled", False))
        switch_frame = ctk.CTkFrame(container, fg_color="white", corner_radius=10)
        switch_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkSwitch(switch_frame, text="启用生理期追踪", variable=self.period_enabled, 
                     font=("Microsoft YaHei UI", 14, "bold"), progress_color="#7EA0B7",
                     command=self.on_period_toggle).pack(anchor="w", padx=15, pady=15)
        
        # 设置区域
        settings_frame = ctk.CTkFrame(container, fg_color="white", corner_radius=10)
        settings_frame.pack(fill="x", pady=(0, 15))
        
        inner = ctk.CTkFrame(settings_frame, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=15)
        
        # 周期长度
        ctk.CTkLabel(inner, text="生理周期（天）", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        self.cycle_slider = ctk.CTkSlider(inner, from_=21, to=35, number_of_steps=14, 
                                         command=self.on_cycle_change)
        self.cycle_slider.set(period_tracker.get("cycle_length", 28))
        self.cycle_slider.pack(fill="x", pady=(0, 5))
        self.cycle_label = ctk.CTkLabel(inner, text=f"{int(self.cycle_slider.get())} 天", 
                                       font=("Microsoft YaHei UI", 11), text_color="gray")
        self.cycle_label.pack(anchor="w", pady=(0, 15))
        
        # 生理期长度
        ctk.CTkLabel(inner, text="生理期长度（天）", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        self.period_length_slider = ctk.CTkSlider(inner, from_=3, to=7, number_of_steps=4,
                                                 command=self.on_period_length_change)
        self.period_length_slider.set(period_tracker.get("period_length", 5))
        self.period_length_slider.pack(fill="x", pady=(0, 5))
        self.period_length_label = ctk.CTkLabel(inner, text=f"{int(self.period_length_slider.get())} 天",
                                               font=("Microsoft YaHei UI", 11), text_color="gray")
        self.period_length_label.pack(anchor="w", pady=(0, 15))
        
        # 上次开始日期
        ctk.CTkLabel(inner, text="生理期开始日期", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        
        date_frame = ctk.CTkFrame(inner, fg_color="transparent")
        date_frame.pack(fill="x", pady=(0, 5))
        
        # 日期输入框
        last_date = period_tracker.get("last_start_date", "")
        self.date_entry = ctk.CTkEntry(date_frame, placeholder_text="YYYY-MM-DD", width=150)
        if last_date:
            self.date_entry.insert(0, last_date)
        self.date_entry.pack(side="left", padx=(0, 5))
        
        # 按钮组
        ctk.CTkButton(date_frame, text="记录今天", width=80, fg_color="#7EA0B7",
                     command=self.record_today).pack(side="left", padx=(0, 5))
        ctk.CTkButton(date_frame, text="保存日期", width=80, fg_color="#6C8EA4",
                     command=self.record_custom_date).pack(side="left")
        
        ctk.CTkLabel(inner, text="提示：可以手动输入过去的日期", 
                    font=("Microsoft YaHei UI", 10), text_color="gray").pack(anchor="w", pady=(0, 10))
        
        # 当前状态显示
        status_frame = ctk.CTkFrame(container, fg_color="white", corner_radius=10)
        status_frame.pack(fill="x", pady=(0, 10))
        
        status_inner = ctk.CTkFrame(status_frame, fg_color="transparent")
        status_inner.pack(fill="x", padx=15, pady=15)
        
        ctk.CTkLabel(status_inner, text="当前状态", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 10))
        self.status_text = ctk.CTkLabel(status_inner, text="", font=("Microsoft YaHei UI", 11), 
                                       text_color="gray", anchor="w", justify="left")
        self.status_text.pack(fill="x")
        
        self.update_period_status_display()
        
        # 保存按钮
        ctk.CTkButton(container, text="保存设置", height=40, fg_color="#7EA0B7",
                     command=self.save_period_settings).pack(fill="x", pady=(10, 0))
    
    def setup_medication_tab(self, parent):
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 顶部
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(header, text="吃药提醒列表", font=("Microsoft YaHei UI", 16, "bold")).pack(side="left")
        ctk.CTkButton(header, text="+ 添加", width=100, fg_color="#7EA0B7", 
                     command=self.add_medication).pack(side="right")
        
        # 列表
        self.med_scroll = ctk.CTkScrollableFrame(container, fg_color="#F2F2F7", corner_radius=15)
        self.med_scroll.pack(fill="both", expand=True)
        
        self.refresh_medication_list()
    
    def on_period_toggle(self):
        # 启用/禁用时更新状态显示
        self.update_period_status_display()
    
    def on_cycle_change(self, value):
        self.cycle_label.configure(text=f"{int(value)} 天")
    
    def on_period_length_change(self, value):
        self.period_length_label.configure(text=f"{int(value)} 天")
    
    def record_today(self):
        """记录今天为生理期开始日"""
        today = datetime.now().strftime("%Y-%m-%d")
        self.cm.record_period_start(today)
        self.date_entry.delete(0, 'end')
        self.date_entry.insert(0, today)
        self.update_period_status_display()
        messagebox.showinfo("成功", "已记录今天为生理期开始日")
    
    def record_custom_date(self):
        """记录自定义日期为生理期开始日"""
        date_str = self.date_entry.get().strip()
        if not date_str:
            messagebox.showwarning("提示", "请输入日期")
            return
        
        # 验证日期格式
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("错误", "日期格式错误，请使用 YYYY-MM-DD 格式，如：2025-12-20")
            return
        
        self.cm.record_period_start(date_str)
        self.update_period_status_display()
        messagebox.showinfo("成功", f"已记录 {date_str} 为生理期开始日")
    
    def update_period_status_display(self):
        if not self.period_enabled.get():
            self.status_text.configure(text="生理期追踪未启用")
            return
        
        status = self.cm.get_period_status()
        
        if status.get("status") == "disabled":
            self.status_text.configure(text="请先记录一次生理期开始日期")
        elif status.get("status") == "in_period":
            day = status.get("period_day", 1)
            self.status_text.configure(text=f"正处于生理期第 {day} 天\n请注意保暖，多喝热水，避免剧烈运动")
        elif status.get("status") == "approaching":
            days = status.get("days_until", 0)
            next_date = status.get("next_date", "")
            self.status_text.configure(text=f"预计 {days} 天后（{next_date}）生理期到来\n建议提前准备卫生用品")
        elif status.get("status") == "normal":
            days = status.get("days_until", 0)
            next_date = status.get("next_date", "")
            self.status_text.configure(text=f"正常期\n预计下次：{next_date}（还有 {days} 天）")
        else:
            self.status_text.configure(text="状态计算出错，请检查设置")
    
    def save_period_settings(self):
        health = self.cm.get("health") or {}
        if "period_tracker" not in health:
            health["period_tracker"] = {}
        
        health["period_tracker"]["enabled"] = self.period_enabled.get()
        health["period_tracker"]["cycle_length"] = int(self.cycle_slider.get())
        health["period_tracker"]["period_length"] = int(self.period_length_slider.get())
        
        self.cm.set("health", health)
        self.update_period_status_display()
        messagebox.showinfo("成功", "生理期设置已保存")
    
    def add_medication(self):
        AddMedicationDialog(self, self.on_medication_added)
    
    def on_medication_added(self, name, times, notes):
        self.cm.add_medication_reminder(name, times, notes)
        self.refresh_medication_list()
        # 通知主窗口重新调度提醒
        if self.app:
            self.app.schedule_medication_reminders()
    
    def refresh_medication_list(self):
        for widget in self.med_scroll.winfo_children():
            widget.destroy()
        
        medications = self.cm.get_medication_reminders()
        
        if not medications:
            empty = ctk.CTkLabel(self.med_scroll, text="暂无吃药提醒\n点击右上角添加", text_color="gray")
            empty.pack(pady=50)
            return
        
        for med in medications:
            self.create_medication_item(med)
    
    def create_medication_item(self, med):
        card = ctk.CTkFrame(self.med_scroll, fg_color="white", corner_radius=10)
        card.pack(fill="x", pady=5, padx=5)
        
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=15, pady=10)
        
        # 药名
        ctk.CTkLabel(info, text=med['name'], font=("Microsoft YaHei UI", 14, "bold"), 
                    text_color="#333333", anchor="w").pack(fill="x")
        
        # 时间
        times_str = ", ".join(med.get("times", []))
        sub_text = f"提醒时间：{times_str}"
        if med.get("notes"):
            sub_text += f"\n备注：{med['notes']}"
        
        ctk.CTkLabel(info, text=sub_text, font=("Microsoft YaHei UI", 11), 
                    text_color="gray", anchor="w", justify="left").pack(fill="x")
        
        # 删除按钮
        ctk.CTkButton(card, text="×", width=30, height=30, fg_color="#FF6B6B", 
                     hover_color="#FF5252", 
                     command=lambda: self.delete_medication(med["id"])).pack(side="right", padx=10)
    
    def delete_medication(self, med_id):
        self.cm.remove_medication_reminder(med_id)
        self.refresh_medication_list()
        if self.app:
            self.app.schedule_medication_reminders()

class AnniversaryManagerWindow(ctk.CTkToplevel):
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.cm = config_manager
        self.title("纪念日管理")
        self.geometry("500x600")
        
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - 500) // 2
            y = (sh - 600) // 2
            self.geometry(f"+{x}+{y}")
        except:
            pass

        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))

        self.setup_ui()
        self.refresh_list()
        
    def setup_ui(self):
        # 顶部
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(header, text="纪念日", font=("Microsoft YaHei UI", 20, "bold")).pack(side="left")
        ctk.CTkButton(header, text="+ 新建纪念日", width=120, fg_color="#7EA0B7", command=self.open_add_dialog).pack(side="right")
        
        # 说明
        info_frame = ctk.CTkFrame(self, fg_color="#FFF9E6", corner_radius=10)
        info_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(info_frame, text="提示：纪念日数据仅存储在本地，打包时不会包含", 
                    font=("Microsoft YaHei UI", 11), text_color="#8B7500").pack(pady=10, padx=10)
        
        # 列表区域
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="#F2F2F7", corner_radius=15)
        self.scroll.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        self.empty_label = ctk.CTkLabel(self.scroll, text="暂无纪念日\n点击右上角新建", text_color="gray")
        
    def refresh_list(self):
        # 清空列表
        for widget in self.scroll.winfo_children():
            widget.destroy()
            
        anniversaries = self.cm.get("anniversaries")
        
        if not anniversaries:
            self.empty_label.pack(pady=50)
            return
            
        for anniv in anniversaries:
            self.create_item(anniv)
            
    def create_item(self, data):
        card = ctk.CTkFrame(self.scroll, fg_color="white", corner_radius=10)
        card.pack(fill="x", pady=5, padx=5)
        
        # 左侧信息
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=15, pady=10)
        
        # 标题
        title_text = data["title"]
        ctk.CTkLabel(info, text=title_text, font=("Microsoft YaHei UI", 14, "bold"), text_color="#333333", anchor="w").pack(fill="x")
        
        # 类型和日期
        type_map = {"birthday": "生日", "period": "生理期", "custom": "其他"}
        type_text = type_map.get(data.get("type", "custom"), "其他")
        sub_text = f"{type_text} • {data['date']}"
        
        if data.get("notes"):
            sub_text += f" • {data['notes']}"
        
        ctk.CTkLabel(info, text=sub_text, font=("Microsoft YaHei UI", 12), text_color="gray", anchor="w").pack(fill="x")
        
        # 右侧删除按钮
        ctk.CTkButton(card, text="×", width=30, height=30, fg_color="#FF6B6B", hover_color="#FF5252", 
                      command=lambda: self.delete_anniversary(data["id"])).pack(side="right", padx=10)
                      
    def open_add_dialog(self):
        AddAnniversaryDialog(self, self.add_anniversary)
        
    def add_anniversary(self, title, date_str, anniversary_type, notes):
        self.cm.add_anniversary(title, date_str, anniversary_type, notes)
        self.refresh_list()
        
    def delete_anniversary(self, anniv_id):
        self.cm.remove_anniversary(anniv_id)
        self.refresh_list()

class SettingsWindow:
    def __init__(self, parent, config_manager, ai_client, callback):
        self.window = ctk.CTkToplevel(parent)
        self.window.title("Project Anmicius Settings")
        self.window.geometry("500x750")
        
        # 居中显示
        try:
            # 尝试居中
            sw = self.window.winfo_screenwidth()
            sh = self.window.winfo_screenheight()
            x = (sw - 500) // 2
            y = (sh - 750) // 2
            self.window.geometry(f"+{x}+{y}")
        except:
            pass
            
        self.cm = config_manager
        self.ai_client = ai_client
        self.callback = callback
        
        self.entries = {}
        self.reminder_vars = {}
        self.schedule_entries = {}
        
        # 懒加载标记：记录哪些标签页已经加载过
        self.tabs_loaded = set()
        
        self.window.attributes('-topmost', True)
        self.window.after(100, lambda: self.window.attributes('-topmost', False))
        self.window.focus_force()

        self.setup_ui()

    def setup_ui(self):
        # 整体容器
        container = ctk.CTkFrame(self.window, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 标题
        title = ctk.CTkLabel(container, text="设置", font=("Microsoft YaHei UI", 24, "bold"), text_color="#333333")
        title.pack(anchor="w", pady=(0, 15))
        
        # Tabview
        self.tabview = ctk.CTkTabview(container, height=550, corner_radius=15, segmented_button_fg_color="#F2F2F7", segmented_button_selected_color="#7EA0B7", segmented_button_unselected_color="#F2F2F7", text_color="#333333")
        self.tabview.pack(fill="both", expand=True)
        
        # 创建标签页（新顺序）
        self.tab_basic = self.tabview.add("基础")
        self.tab_character = self.tabview.add("角色")
        self.tab_touch = self.tabview.add("触摸")
        self.tab_daily = self.tabview.add("日常")
        self.tab_reminder = self.tabview.add("提醒")
        
        # 绑定标签页切换事件（懒加载）
        self.tabview.configure(command=self.on_tab_change)
        
        # --- 只加载第一个标签页（基础） ---
        self.setup_basic_tab(self.tab_basic)
        self.tabs_loaded.add("基础")

        # --- 底部保存按钮 ---
        save_btn = ctk.CTkButton(
            container, 
            text="保存并应用", 
            command=self.save_settings, 
            height=45, 
            corner_radius=22,
            font=("Microsoft YaHei UI", 15, "bold"),
            fg_color="#7EA0B7",
            hover_color="#6C8EA4"
        )
        save_btn.pack(fill="x", pady=(20, 0))

    def on_tab_change(self):
        """标签页切换时的懒加载处理"""
        # 获取当前选中的标签页名称
        tab_name = self.tabview.get()
        
        # 如果这个标签页已经加载过，直接返回
        if tab_name in self.tabs_loaded:
            return
        
        # 根据标签页名称加载对应内容
        tab_setup_map = {
            "基础": (self.setup_basic_tab, self.tab_basic),
            "角色": (self.setup_character_tab, self.tab_character),
            "触摸": (self.setup_touch_tab, self.tab_touch),
            "日常": (self.setup_daily_tab, self.tab_daily),
            "提醒": (self.setup_reminder_tab, self.tab_reminder)
        }
        
        if tab_name in tab_setup_map:
            setup_func, tab_widget = tab_setup_map[tab_name]
            setup_func(tab_widget)
            self.tabs_loaded.add(tab_name)
            logging.info(f"Lazy loaded tab: {tab_name}")

    def setup_basic_tab(self, parent):
        """基础设置标签页：API连接 + 天气 + 外观"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        
        # === API 设置 ===
        api_card = self.create_card(scroll, pady=10)
        
        self.create_section_label(api_card, "模型接入")
        
        # API Base URL
        self.create_input_row(api_card, "API 地址", "api_base_url", self.cm.get("api_base_url"))
        
        # API Key
        self.create_input_row(api_card, "API Key", "api_key", self.cm.get("api_key"), show="*")
        
        # 模型选择
        model_frame = ctk.CTkFrame(api_card, fg_color="transparent")
        model_frame.pack(fill="x", pady=10)
        ctk.CTkLabel(model_frame, text="模型名称", width=80, anchor="w", font=("Microsoft YaHei UI", 12), text_color="gray").pack(side="left")
        
        self.model_combo = ctk.CTkComboBox(model_frame, values=[self.cm.get("model")], width=200, border_width=0, fg_color="#F2F2F7", text_color="#333333")
        self.model_combo.pack(side="left", fill="x", expand=True, padx=5)
        self.model_combo.set(self.cm.get("model"))
        
        ctk.CTkButton(model_frame, text="刷新", width=60, command=self.refresh_models, fg_color="#F2F2F7", text_color="#333333", hover_color="#E5E5EA").pack(side="right")

        # 历史消息数量
        self.create_input_row(api_card, "历史消息数", "max_history_messages", self.cm.get("max_history_messages", 10))
        ctk.CTkLabel(api_card, text="注：对话时发送给AI的历史消息条数(1-50)，越多越费Token。", font=("Microsoft YaHei UI", 10), text_color="gray").pack(anchor="w", padx=85, pady=(0, 15))

        self.create_section_label(api_card, "天气服务 (可选)")
        self.create_input_row(api_card, "城市名称", "weather_city", self.cm.get("weather_city", ""))
        ctk.CTkLabel(api_card, text="注：留空则不播报天气。可直接填城市名(如:北京)。", font=("Microsoft YaHei UI", 10), text_color="gray").pack(anchor="w", padx=85, pady=(0, 10))
        self.create_input_row(api_card, "和风 Key", "weather_api_key", self.cm.get("weather_api_key", ""), show="*")
        
        # 添加"前往获取"按钮
        btn_frame = ctk.CTkFrame(api_card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=85, pady=(5, 10))
        ctk.CTkButton(
            btn_frame, 
            text="前往获取和风 Key", 
            width=150,
            height=28,
            corner_radius=14,
            fg_color="#7EA0B7",
            hover_color="#6C8EA4",
            font=("Microsoft YaHei UI", 11),
            command=lambda: webbrowser.open("https://dev.qweather.com/")
        ).pack(side="left")
        
        ctk.CTkLabel(api_card, text="注：填入和风天气Key可获更准数据，不填则使用免费源。", font=("Microsoft YaHei UI", 10), text_color="gray").pack(anchor="w", padx=85, pady=(0, 10))
        
        # === 外观设置 ===
        appearance_card = self.create_card(scroll, pady=10)
        
        # 获取当前配置
        appearance = self.cm.get("appearance") or {}
        bubble_style = appearance.get("bubble", {})
        input_style = appearance.get("input_box", {})
        
        # ===== 气泡样式 =====
        self.create_section_label(appearance_card, "对话气泡样式")
        
        # 颜色配置
        self.create_color_input(appearance_card, "背景颜色", "bubble_bg", bubble_style.get("background_color", "#FFFFFF"))
        self.create_color_input(appearance_card, "边框颜色", "bubble_border", bubble_style.get("border_color", "#646464"))
        self.create_color_input(appearance_card, "文字颜色", "bubble_text", bubble_style.get("text_color", "#323232"))
        
        # 数值配置
        self.create_slider_input(appearance_card, "圆角大小", "bubble_corner", bubble_style.get("corner_radius", 14), 0, 30)
        self.create_slider_input(appearance_card, "水平内边距", "bubble_padding_x", bubble_style.get("padding_x", 30), 10, 50)
        self.create_slider_input(appearance_card, "垂直内边距", "bubble_padding_y", bubble_style.get("padding_y", 28), 10, 50)
        self.create_slider_input(appearance_card, "字体大小", "bubble_font", bubble_style.get("font_size", 14), 10, 20)
        self.create_slider_input(appearance_card, "边框粗细", "bubble_border_width", bubble_style.get("border_width", 1), 0, 5)
        
        # 字体配置
        self.create_font_selector(appearance_card, "字体设置", "bubble_font", 
                                 bubble_style.get("font_type", "custom"),
                                 bubble_style.get("font_name", "Microsoft YaHei UI"),
                                 bubble_style.get("font_file", ""))
        
        # ===== 输入框样式 =====
        self.create_section_label(appearance_card, "输入框样式")
        
        # 颜色配置
        self.create_color_input(appearance_card, "背景颜色", "input_bg", input_style.get("background_color", "#FFFFFF"))
        self.create_color_input(appearance_card, "边框颜色", "input_border", input_style.get("border_color", "#E5E5E5"))
        self.create_color_input(appearance_card, "文字颜色", "input_text", input_style.get("text_color", "#333333"))
        self.create_color_input(appearance_card, "按钮颜色", "input_button", input_style.get("button_color", "#7EA0B7"))
        self.create_color_input(appearance_card, "按钮悬停色", "input_button_hover", input_style.get("button_hover_color", "#6C8EA4"))
        
        # 数值配置
        self.create_slider_input(appearance_card, "圆角大小", "input_corner", input_style.get("corner_radius", 30), 0, 40)
        self.create_slider_input(appearance_card, "字体大小", "input_font", input_style.get("font_size", 13), 10, 18)
        
        # 重置按钮
        reset_frame = ctk.CTkFrame(appearance_card, fg_color="transparent")
        reset_frame.pack(fill="x", pady=10)
        ctk.CTkButton(reset_frame, text="恢复默认外观", fg_color="#FF6B6B", hover_color="#FF5252",
                     command=self.reset_appearance).pack()

    def setup_daily_tab(self, parent):
        """日常计划标签页：喝水目标 + 工作时间"""
        card = self.create_card(parent)
        
        self.create_section_label(card, "每日目标")
        self.create_input_row(card, "喝水目标 (杯)", "daily_target_cups", str(self.cm.get("daily_target_cups")))
        
        ctk.CTkFrame(card, height=1, fg_color="#F2F2F7").pack(fill="x", pady=15) # 分割线
        
        self.create_section_label(card, "每周计划")
        
        # 滚动区域显示周计划
        scroll = ctk.CTkScrollableFrame(card, fg_color="transparent", height=250)
        scroll.pack(fill="both", expand=True)
        
        weekly_schedule = self.cm.get("weekly_schedule")
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        
        for day, day_cn in zip(days, day_names):
            day_config = weekly_schedule.get(day, {"enabled": True, "start": "09:00", "end": "18:00"})
            
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=5)
            
            # 开关
            enabled_var = ctk.BooleanVar(value=day_config.get("enabled", True))
            self.schedule_entries[f"{day}_enabled"] = enabled_var
            
            switch = ctk.CTkSwitch(row, text=day_cn, variable=enabled_var, width=80, font=("Microsoft YaHei UI", 13, "bold"), progress_color="#7EA0B7")
            switch.pack(side="left")
            
            # 时间输入
            time_box = ctk.CTkFrame(row, fg_color="#F2F2F7", corner_radius=8)
            time_box.pack(side="right", fill="x", expand=True, padx=(10, 0))
            
            start_entry = ctk.CTkEntry(time_box, width=50, height=28, border_width=0, fg_color="transparent", justify="center")
            start_entry.insert(0, day_config.get("start", "09:00"))
            start_entry.pack(side="left", padx=5)
            self.schedule_entries[f"{day}_start"] = start_entry
            
            ctk.CTkLabel(time_box, text="-", text_color="gray").pack(side="left")
            
            end_entry = ctk.CTkEntry(time_box, width=50, height=28, border_width=0, fg_color="transparent", justify="center")
            end_entry.insert(0, day_config.get("end", "18:00"))
            end_entry.pack(side="left", padx=5)
            self.schedule_entries[f"{day}_end"] = end_entry

    def setup_reminder_tab(self, parent):
        reminders = self.cm.get("reminders")
        
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        
        # 吃饭
        self.create_reminder_card(scroll, "meal", "吃饭提醒", reminders, 
                               "提醒时间 (逗号分隔)", 
                               ", ".join(reminders.get("meal", {}).get("times", ["08:00", "12:00", "18:30"])),
                               "meal_times")

        # 久坐
        self.create_reminder_card(scroll, "sitting", "久坐提醒", reminders,
                               "间隔 (分钟)",
                               str(reminders.get("sitting", {}).get("interval", 45)),
                               "sitting_interval")
        
        # 放松
        self.create_reminder_card(scroll, "relax", "放松提醒", reminders,
                               "间隔 (分钟)",
                               str(reminders.get("relax", {}).get("interval", 90)),
                               "relax_interval")
        
        # 闲聊
        chat_card = self.create_card(scroll, pady=10)
        self.chat_var = ctk.BooleanVar(value=self.cm.get("enable_random_chat"))
        ctk.CTkSwitch(chat_card, text="随机闲聊", variable=self.chat_var, font=("Microsoft YaHei UI", 14, "bold"), progress_color="#7EA0B7").pack(anchor="w", pady=(0, 10))
        
        interval_row = ctk.CTkFrame(chat_card, fg_color="transparent")
        interval_row.pack(fill="x")
        ctk.CTkLabel(interval_row, text="间隔 (分钟)", text_color="gray", width=100, anchor="w").pack(side="left")
        
        chat_entry = ctk.CTkEntry(interval_row, width=100, border_width=0, fg_color="#F2F2F7")
        chat_entry.insert(0, str(self.cm.get("random_chat_interval")))
        chat_entry.pack(side="right", fill="x", expand=True)
        self.entries["random_chat_interval"] = chat_entry
        
        # 分割线
        ctk.CTkFrame(scroll, height=2, fg_color="#E5E5EA").pack(fill="x", pady=20)
        
        # 自定义提醒区域
        custom_card = self.create_card(scroll, pady=10)
        
        # 标题和新建按钮
        header = ctk.CTkFrame(custom_card, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))
        
        self.create_section_label_in_frame(header, "自定义提醒")
        ctk.CTkButton(
            header, 
            text="+ 新建提醒", 
            width=100,
            height=28,
            corner_radius=14,
            fg_color="#7EA0B7",
            hover_color="#6C8EA4",
            font=("Microsoft YaHei UI", 12),
            command=self.add_custom_reminder
        ).pack(side="right")
        
        # 自定义提醒列表容器
        self.custom_reminders_frame = ctk.CTkFrame(custom_card, fg_color="transparent")
        self.custom_reminders_frame.pack(fill="both", expand=True)
        
        # 加载现有的自定义提醒
        self.refresh_custom_reminders_display()
    
    def create_section_label_in_frame(self, parent, text):
        """在指定父容器中创建区域标签"""
        label = ctk.CTkLabel(parent, text=text, font=("Microsoft YaHei UI", 14, "bold"), text_color="#333333", anchor="w")
        label.pack(side="left")
        return label
    
    def refresh_custom_reminders_display(self):
        """刷新自定义提醒显示"""
        # 清空现有显示
        for widget in self.custom_reminders_frame.winfo_children():
            widget.destroy()
        
        custom_reminders = self.cm.get("reminders").get("custom", [])
        
        if not custom_reminders:
            empty_label = ctk.CTkLabel(
                self.custom_reminders_frame, 
                text="暂无自定义提醒\n点击右上角「+ 新建提醒」添加",
                text_color="gray",
                font=("Microsoft YaHei UI", 11)
            )
            empty_label.pack(pady=20)
            return
        
        # 显示每个提醒
        for reminder in custom_reminders:
            self.create_custom_reminder_item(reminder)
    
    def create_custom_reminder_item(self, reminder):
        """创建单个自定义提醒项"""
        item_frame = ctk.CTkFrame(self.custom_reminders_frame, fg_color="#F9F9FA", corner_radius=8)
        item_frame.pack(fill="x", pady=5)
        
        # 左侧信息
        info_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=10, pady=8)
        
        # 内容
        ctk.CTkLabel(
            info_frame, 
            text=reminder["content"], 
            font=("Microsoft YaHei UI", 12, "bold"),
            text_color="#333333",
            anchor="w"
        ).pack(fill="x")
        
        # 详情
        next_time = datetime.fromisoformat(reminder["next_trigger_time"]).strftime("%H:%M") if reminder.get("next_trigger_time") else "即将触发"
        detail_text = f"每 {reminder['interval']} 分钟 · 剩余 {reminder['remaining_count']} 次 · 下次 {next_time}"
        ctk.CTkLabel(
            info_frame,
            text=detail_text,
            font=("Microsoft YaHei UI", 10),
            text_color="gray",
            anchor="w"
        ).pack(fill="x")
        
        # 右侧删除按钮
        ctk.CTkButton(
            item_frame,
            text="×",
            width=30,
            height=30,
            corner_radius=15,
            fg_color="#FF6B6B",
            hover_color="#FF5252",
            font=("Arial", 16),
            command=lambda: self.delete_custom_reminder(reminder["id"])
        ).pack(side="right", padx=10)
    
    def add_custom_reminder(self):
        """打开添加自定义提醒对话框"""
        AddReminderDialog(self.window, self.on_custom_reminder_added)
    
    def on_custom_reminder_added(self, content, interval, count):
        """自定义提醒添加回调"""
        reminders = self.cm.get("reminders")
        if "custom" not in reminders:
            reminders["custom"] = []
        
        new_reminder = {
            "id": str(uuid.uuid4()),
            "content": content,
            "interval": interval,
            "remaining_count": count,
            "next_trigger_time": (datetime.now() + timedelta(minutes=interval)).isoformat()
        }
        
        reminders["custom"].append(new_reminder)
        self.cm.set("reminders", reminders)
        
        # 刷新显示
        self.refresh_custom_reminders_display()
        
        # 通知主窗口更新调度（如果有callback）
        if self.callback:
            self.callback()
    
    def delete_custom_reminder(self, reminder_id):
        """删除自定义提醒"""
        reminders = self.cm.get("reminders")
        custom_list = reminders.get("custom", [])
        reminders["custom"] = [r for r in custom_list if r["id"] != reminder_id]
        self.cm.set("reminders", reminders)
        
        # 刷新显示
        self.refresh_custom_reminders_display()
        
        # 通知主窗口更新调度
        if self.callback:
            self.callback()
    
    def setup_touch_tab(self, parent):
        """触摸互动设置标签页"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        
        card = self.create_card(scroll, pady=10)
        
        self.create_section_label(card, "触摸互动功能")
        
        # 功能开关
        touch_config = self.cm.get("touch_areas") or {"enabled": True, "areas": []}
        self.touch_enabled_var = ctk.BooleanVar(value=touch_config.get("enabled", True))
        
        switch_frame = ctk.CTkFrame(card, fg_color="transparent")
        switch_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkSwitch(switch_frame, text="启用触摸互动", variable=self.touch_enabled_var, 
                     font=("Microsoft YaHei UI", 14, "bold"), progress_color="#7EA0B7").pack(side="left")
        
        ctk.CTkLabel(switch_frame, text="点击立绘时触发AI反应", text_color="gray", 
                    font=("Microsoft YaHei UI", 11)).pack(side="left", padx=(10, 0))
        
        ctk.CTkFrame(card, height=1, fg_color="#F2F2F7").pack(fill="x", pady=15)
        
        # 区域配置
        self.create_section_label(card, "触摸区域配置")
        
        info_frame = ctk.CTkFrame(card, fg_color="#E8F4F8", corner_radius=8)
        info_frame.pack(fill="x", pady=(0, 15))
        
        areas = touch_config.get("areas", [])
        area_count = len(areas)
        
        ctk.CTkLabel(info_frame, text=f"当前已配置 {area_count} 个触摸区域", 
                    font=("Microsoft YaHei UI", 12), text_color="#333333").pack(pady=10)
        
        if area_count > 0:
            area_names = [area.get("name", f"区域{i+1}") for i, area in enumerate(areas)]
            area_text = "、".join(area_names[:5])
            if area_count > 5:
                area_text += f" 等{area_count}个区域"
            
            ctk.CTkLabel(info_frame, text=area_text, font=("Microsoft YaHei UI", 11), 
                        text_color="gray", wraplength=400).pack(pady=(0, 10))
        
        # 编辑按钮
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x")
        
        ctk.CTkButton(btn_frame, text="打开可视化编辑器", height=45, corner_radius=22,
                     font=("Microsoft YaHei UI", 14, "bold"), fg_color="#7EA0B7", 
                     hover_color="#6C8EA4", command=self.open_touch_editor).pack(fill="x")
        
        ctk.CTkLabel(card, text="提示：在编辑器中可以在立绘上拖动鼠标绘制触摸区域", 
                    text_color="gray", font=("Microsoft YaHei UI", 10), 
                    wraplength=400).pack(pady=(10, 0))
    
    def open_touch_editor(self):
        """打开触摸区域编辑器"""
        TouchAreaEditorWindow(self.window, self.cm, self.refresh_touch_info)
    
    def refresh_touch_info(self):
        """刷新触摸区域信息显示"""
        # 重新加载触摸配置并更新显示
        # 这里可以选择重新构建整个标签页，或者只更新特定部分
        # 简化处理：提示用户
        messagebox.showinfo("提示", "触摸区域已更新！请点击'保存并应用'使更改生效。")

    def create_color_input(self, parent, label, key, default_value):
        """创建颜色输入行"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(frame, text=label, width=100, anchor="w", font=("Microsoft YaHei UI", 12), text_color="gray").pack(side="left")
        
        entry = ctk.CTkEntry(frame, width=100, border_width=0, fg_color="#F2F2F7", text_color="#333333")
        entry.insert(0, default_value)
        entry.pack(side="left", padx=5)
        
        # 颜色预览
        color_preview = ctk.CTkLabel(frame, text="    ", width=30, height=20, fg_color=default_value, corner_radius=5)
        color_preview.pack(side="left", padx=5)
        
        # 更新预览
        def update_preview(*args):
            try:
                color = entry.get()
                color_preview.configure(fg_color=color)
            except:
                pass
        
        entry.bind("<KeyRelease>", update_preview)
        
        self.entries[key] = entry
    
    def create_slider_input(self, parent, label, key, default_value, min_val, max_val):
        """创建滑块输入行"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=5)
        
        label_widget = ctk.CTkLabel(frame, text=f"{label}: {default_value}", width=150, anchor="w", 
                                    font=("Microsoft YaHei UI", 12), text_color="gray")
        label_widget.pack(side="left")
        
        slider = ctk.CTkSlider(frame, from_=min_val, to=max_val, 
                              number_of_steps=max_val-min_val,
                              command=lambda v: label_widget.configure(text=f"{label}: {int(v)}"))
        slider.set(default_value)
        slider.pack(side="left", fill="x", expand=True, padx=5)
        
        self.entries[key] = slider
    
    def create_font_selector(self, parent, label, key_prefix, default_type, default_name, default_file):
        """创建字体选择器"""
        frame = ctk.CTkFrame(parent, fg_color="#F8F9FA", corner_radius=10)
        frame.pack(fill="x", pady=10, padx=10)
        
        # 标题
        ctk.CTkLabel(frame, text=label, font=("Microsoft YaHei UI", 12, "bold"), 
                    text_color="#333333").pack(anchor="w", padx=10, pady=(10, 5))
        
        # 字体类型选择
        type_frame = ctk.CTkFrame(frame, fg_color="transparent")
        type_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(type_frame, text="字体类型", width=100, anchor="w", 
                    font=("Microsoft YaHei UI", 12), text_color="gray").pack(side="left")
        
        font_type_var = tk.StringVar(value=default_type)
        type_radio_frame = ctk.CTkFrame(type_frame, fg_color="transparent")
        type_radio_frame.pack(side="left", padx=5)
        
        ctk.CTkRadioButton(type_radio_frame, text="系统字体", variable=font_type_var, 
                          value="system").pack(side="left", padx=5)
        ctk.CTkRadioButton(type_radio_frame, text="自定义字体文件", variable=font_type_var, 
                          value="custom").pack(side="left", padx=5)
        
        # 系统字体选择
        sys_font_frame = ctk.CTkFrame(frame, fg_color="transparent")
        sys_font_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(sys_font_frame, text="系统字体", width=100, anchor="w", 
                    font=("Microsoft YaHei UI", 12), text_color="gray").pack(side="left")
        
        system_fonts = [
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "SimHei",
            "SimSun",
            "KaiTi",
            "FangSong",
            "Arial",
            "Times New Roman",
            "Courier New"
        ]
        
        font_name_var = tk.StringVar(value=default_name)
        font_combo = ctk.CTkComboBox(sys_font_frame, values=system_fonts, variable=font_name_var,
                                    width=200, state="readonly")
        font_combo.pack(side="left", padx=5)
        
        # 自定义字体文件
        custom_font_frame = ctk.CTkFrame(frame, fg_color="transparent")
        custom_font_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(custom_font_frame, text="字体文件", width=100, anchor="w", 
                    font=("Microsoft YaHei UI", 12), text_color="gray").pack(side="left")
        
        font_file_entry = ctk.CTkEntry(custom_font_frame, placeholder_text="点击'浏览'选择字体文件...")
        if default_file:
            font_file_entry.insert(0, default_file)
        font_file_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        def browse_font():
            file_path = filedialog.askopenfilename(
                title="选择字体文件",
                filetypes=[("字体文件", "*.ttf;*.ttc;*.otf"), ("所有文件", "*.*")]
            )
            if file_path:
                font_file_entry.delete(0, "end")
                font_file_entry.insert(0, file_path)
        
        ctk.CTkButton(custom_font_frame, text="浏览", width=80, height=30, 
                     fg_color="#FF9800", hover_color="#F57C00",
                     command=browse_font).pack(side="left", padx=5)
        
        # 说明文字
        info_label = ctk.CTkLabel(frame, 
                                 text="提示：选择'系统字体'使用Windows系统字体，选择'自定义字体文件'可以使用任何TTF/OTF字体",
                                 font=("Microsoft YaHei UI", 10), text_color="#666666", wraplength=600)
        info_label.pack(pady=(5, 10), padx=10)
        
        # 保存引用
        self.entries[f"{key_prefix}_type"] = font_type_var
        self.entries[f"{key_prefix}_name"] = font_name_var
        self.entries[f"{key_prefix}_file"] = font_file_entry
    
    def reset_appearance(self):
        """重置为默认外观"""
        if messagebox.askyesno("确认", "确定要恢复默认外观吗？"):
            # 设置默认值
            default_appearance = {
                "bubble": {
                    "background_color": "#FFFFFF",
                    "border_color": "#646464",
                    "text_color": "#323232",
                    "corner_radius": 14,
                    "font_type": "custom",
                    "font_name": "Microsoft YaHei UI",
                    "font_file": "",
                    "padding_x": 30,
                    "padding_y": 28,
                    "font_size": 14,
                    "border_width": 1
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
            self.cm.set("appearance", default_appearance)
            messagebox.showinfo("成功", "已恢复默认外观，请重启程序生效")

    def setup_expression_tab(self, parent):
        scroll_container = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll_container.pack(fill="both", expand=True)
        
        card = self.create_card(scroll_container)
        
        self.create_section_label(card, "表情系统设置")
        
        # 默认立绘
        ctk.CTkLabel(card, text="默认立绘", font=("Microsoft YaHei UI", 12), text_color="gray").pack(anchor="w")
        default_frame = ctk.CTkFrame(card, fg_color="transparent")
        default_frame.pack(fill="x", pady=(5, 15))
        
        expressions_config = self.cm.get("expressions") or {"default": "character.png", "mappings": {}, "restore_delay": 5}
        
        self.entry_default_img = ctk.CTkEntry(default_frame)
        self.entry_default_img.insert(0, expressions_config.get("default", "character.png"))
        self.entry_default_img.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ctk.CTkButton(default_frame, text="浏览", width=60, fg_color="#7EA0B7", command=self.browse_default_image).pack(side="right")
        
        # 恢复延迟
        delay_frame = ctk.CTkFrame(card, fg_color="transparent")
        delay_frame.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(delay_frame, text="表情恢复延迟（秒）", font=("Microsoft YaHei UI", 12), text_color="gray").pack(side="left", padx=(0, 10))
        self.entry_restore_delay = ctk.CTkEntry(delay_frame, width=80)
        self.entry_restore_delay.insert(0, str(expressions_config.get("restore_delay", 5)))
        self.entry_restore_delay.pack(side="right")
        
        ctk.CTkFrame(card, height=1, fg_color="#F2F2F7").pack(fill="x", pady=15)
        
        # 表情映射
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))
        
        self.create_section_label(header, "表情映射")
        ctk.CTkButton(header, text="+ 添加表情", height=30, fg_color="#7EA0B7", command=self.add_expression_mapping).pack(side="right")
        
        ctk.CTkLabel(card, text="AI回复中的 [表情] 标签会触发对应的立绘切换", text_color="gray", font=("Microsoft YaHei UI", 11)).pack(anchor="w", pady=(0, 10))
        
        # 列表区域
        self.expr_scroll = ctk.CTkScrollableFrame(card, fg_color="#F2F2F7", height=200)
        self.expr_scroll.pack(fill="x", expand=False)
        
        self.refresh_expression_list()
    
    def browse_default_image(self):
        file_path = filedialog.askopenfilename(
            title="选择默认立绘",
            filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.webp")]
        )
        if file_path:
            self.entry_default_img.delete(0, 'end')
            self.entry_default_img.insert(0, file_path)
    
    def refresh_expression_list(self):
        for widget in self.expr_scroll.winfo_children():
            widget.destroy()
        
        expressions_config = self.cm.get("expressions") or {"default": "character.png", "mappings": {}, "restore_delay": 5}
        mappings = expressions_config.get("mappings", {})
        
        if not mappings:
            empty = ctk.CTkLabel(self.expr_scroll, text="暂无表情映射\n点击右上角添加", text_color="gray")
            empty.pack(pady=30)
            return
        
        for keyword, path in mappings.items():
            self.create_expression_item(keyword, path)
    
    def create_expression_item(self, keyword, path):
        item = ctk.CTkFrame(self.expr_scroll, fg_color="white", corner_radius=5)
        item.pack(fill="x", pady=2, padx=2)
        
        info_frame = ctk.CTkFrame(item, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=10, pady=8)
        
        ctk.CTkLabel(info_frame, text=f"[{keyword}]", font=("Microsoft YaHei UI", 13, "bold"), text_color="#7EA0B7", anchor="w").pack(fill="x")
        
        path_display = path if len(path) <= 40 else "..." + path[-37:]
        ctk.CTkLabel(info_frame, text=path_display, font=("Microsoft YaHei UI", 11), text_color="gray", anchor="w").pack(fill="x")
        
        # 删除按钮
        ctk.CTkButton(item, text="×", width=25, height=25, fg_color="#FF6B6B", hover_color="#FF5252", 
                     command=lambda k=keyword: self.delete_expression_mapping(k)).pack(side="right", padx=5)
        
        # 双击编辑
        item.bind("<Double-Button-1>", lambda e, k=keyword, p=path: self.edit_expression_mapping(k, p))
        for child in info_frame.winfo_children():
            child.bind("<Double-Button-1>", lambda e, k=keyword, p=path: self.edit_expression_mapping(k, p))
    
    def add_expression_mapping(self):
        ExpressionDialog(self.window, None, self.save_expression_mapping)
    
    def edit_expression_mapping(self, keyword, path):
        ExpressionDialog(self.window, {"keyword": keyword, "path": path}, 
                        lambda data: self.save_expression_mapping(data, old_keyword=keyword))
    
    def save_expression_mapping(self, data, old_keyword=None):
        expressions_config = self.cm.get("expressions") or {"default": "character.png", "mappings": {}, "restore_delay": 5}
        mappings = expressions_config.get("mappings", {})
        
        # 如果是编辑，删除旧的
        if old_keyword and old_keyword in mappings:
            del mappings[old_keyword]
        
        # 添加新的
        mappings[data["keyword"]] = data["path"]
        
        expressions_config["mappings"] = mappings
        self.cm.set("expressions", expressions_config)
        self.refresh_expression_list()
    
    def delete_expression_mapping(self, keyword):
        expressions_config = self.cm.get("expressions") or {"default": "character.png", "mappings": {}, "restore_delay": 5}
        mappings = expressions_config.get("mappings", {})
        
        if keyword in mappings:
            del mappings[keyword]
            expressions_config["mappings"] = mappings
            self.cm.set("expressions", expressions_config)
            self.refresh_expression_list()

    def setup_character_tab(self, parent):
        """角色设置标签页：角色信息 + 表情系统"""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        
        # === 角色信息 ===
        character_card = self.create_card(scroll, expand=True)
        
        self.create_section_label(character_card, "角色名称")
        ctk.CTkLabel(character_card, text="当前角色的名字（可在提示词中使用{char}变量）", text_color="gray", font=("Microsoft YaHei UI", 11)).pack(anchor="w", pady=(0, 5))
        
        self.entry_char_name = ctk.CTkEntry(character_card, height=35, border_width=0, fg_color="#F2F2F7", corner_radius=10, 
                                            placeholder_text="例如：梁俊杰、猫娘...")
        current_char = self.cm.get_current_character()
        self.entry_char_name.insert(0, current_char.get("name", "角色") if current_char else "角色")
        self.entry_char_name.pack(fill="x", pady=(0, 15))
        
        self.create_section_label(character_card, "AI 人设")
        ctk.CTkLabel(character_card, text="AI 扮演的角色设定", text_color="gray", font=("Microsoft YaHei UI", 11)).pack(anchor="w", pady=(0, 5))
        
        self.txt_persona = ctk.CTkTextbox(character_card, height=100, border_width=0, fg_color="#F2F2F7", corner_radius=10, font=("Microsoft YaHei UI", 12))
        self.txt_persona.insert("1.0", self.cm.get("persona"))
        self.txt_persona.pack(fill="x", pady=(0, 10))
        
        self.create_section_label(character_card, "用户名称")
        ctk.CTkLabel(character_card, text="AI如何称呼你（可在提示词中使用{user}变量）", text_color="gray", font=("Microsoft YaHei UI", 11)).pack(anchor="w", pady=(0, 5))
        
        self.entry_user_name = ctk.CTkEntry(character_card, height=35, border_width=0, fg_color="#F2F2F7", corner_radius=10, 
                                            placeholder_text="例如：小明、月月、主人...")
        self.entry_user_name.insert(0, self.cm.get("user_name") or "用户")
        self.entry_user_name.pack(fill="x", pady=(0, 15))
        
        self.create_section_label(character_card, "用户身份")
        ctk.CTkLabel(character_card, text="你在对话中的身份及关系", text_color="gray", font=("Microsoft YaHei UI", 11)).pack(anchor="w", pady=(0, 5))
        
        self.txt_user_identity = ctk.CTkTextbox(character_card, height=60, border_width=0, fg_color="#F2F2F7", corner_radius=10, font=("Microsoft YaHei UI", 12))
        self.txt_user_identity.insert("1.0", self.cm.get("user_identity") or "")
        self.txt_user_identity.pack(fill="x", pady=(0, 10))
        
        # --- Lorebook (背景知识) ---
        self.create_section_label(character_card, "世界书 (Lorebook)")
        ctk.CTkLabel(character_card, text="设置背景知识，可常驻或通过关键词触发", text_color="gray", font=("Microsoft YaHei UI", 11)).pack(anchor="w", pady=(0, 5))
        
        # 列表区域 - 固定高度，不自动扩展，防止挤压按钮
        self.lore_scroll = ctk.CTkScrollableFrame(character_card, fg_color="#F2F2F7", height=180)
        self.lore_scroll.pack(fill="x", expand=False, pady=(0, 10))
        
        # 按钮区域
        btn_frame = ctk.CTkFrame(character_card, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkButton(btn_frame, text="+ 添加条目", height=35, fg_color="#7EA0B7", command=self.add_lore_entry).pack(side="left")
        ctk.CTkLabel(btn_frame, text="双击条目编辑，右侧按钮删除", text_color="gray", font=("Microsoft YaHei UI", 11)).pack(side="right")

        self.refresh_lore_list()
        
        # === 表情系统 ===
        expression_card = self.create_card(scroll, pady=10)
        
        self.create_section_label(expression_card, "表情系统设置")
        
        # 默认立绘
        ctk.CTkLabel(expression_card, text="默认立绘", font=("Microsoft YaHei UI", 12), text_color="gray").pack(anchor="w")
        default_frame = ctk.CTkFrame(expression_card, fg_color="transparent")
        default_frame.pack(fill="x", pady=(5, 15))
        
        expressions_config = self.cm.get("expressions") or {"default": "character.png", "mappings": {}, "restore_delay": 5}
        
        self.entry_default_img = ctk.CTkEntry(default_frame)
        self.entry_default_img.insert(0, expressions_config.get("default", "character.png"))
        self.entry_default_img.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ctk.CTkButton(default_frame, text="浏览", width=60, fg_color="#7EA0B7", command=self.browse_default_image).pack(side="right")
        
        # 恢复延迟
        delay_frame = ctk.CTkFrame(expression_card, fg_color="transparent")
        delay_frame.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(delay_frame, text="表情恢复延迟（秒）", font=("Microsoft YaHei UI", 12), text_color="gray").pack(side="left", padx=(0, 10))
        self.entry_restore_delay = ctk.CTkEntry(delay_frame, width=80)
        self.entry_restore_delay.insert(0, str(expressions_config.get("restore_delay", 5)))
        self.entry_restore_delay.pack(side="right")
        
        ctk.CTkFrame(expression_card, height=1, fg_color="#F2F2F7").pack(fill="x", pady=15)
        
        # 表情映射
        header = ctk.CTkFrame(expression_card, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))
        
        self.create_section_label(header, "表情映射")
        ctk.CTkButton(header, text="+ 添加表情", height=30, fg_color="#7EA0B7", command=self.add_expression_mapping).pack(side="right")
        
        ctk.CTkLabel(expression_card, text="AI回复中的 [表情] 标签会触发对应的立绘切换", text_color="gray", font=("Microsoft YaHei UI", 11)).pack(anchor="w", pady=(0, 10))
        
        # 列表区域
        self.expr_scroll = ctk.CTkScrollableFrame(expression_card, fg_color="#F2F2F7", height=200)
        self.expr_scroll.pack(fill="x", expand=False)
        
        self.refresh_expression_list()

    def refresh_lore_list(self):
        for widget in self.lore_scroll.winfo_children():
            widget.destroy()
            
        lorebook = self.cm.get("lorebook") or []
        for i, entry in enumerate(lorebook):
            self.create_lore_item(i, entry)
            
    def create_lore_item(self, index, entry):
        bg_color = "white"
        
        item = ctk.CTkFrame(self.lore_scroll, fg_color=bg_color, corner_radius=5)
        item.pack(fill="x", pady=2, padx=2)
        
        # 类型标识
        type_text = "常驻" if entry.get("type") == "always" else "触发"
        type_color = "#7EA0B7" if entry.get("type") == "always" else "#FFB6C1"
        
        ctk.CTkLabel(item, text=type_text, fg_color=type_color, text_color="white", corner_radius=4, font=("Microsoft YaHei UI", 10), width=40).pack(side="left", padx=5, pady=5)
        
        # 关键词/内容摘要
        if entry.get("type") == "keyword":
            keywords = entry.get("keywords", "")
            if len(keywords) > 15: keywords = keywords[:15] + "..."
            title = f"[{keywords}]"
        else:
            title = "全局生效"
            
        content = entry.get("content", "")
        if len(content) > 20: content = content[:20] + "..."
        
        info_frame = ctk.CTkFrame(item, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=5)
        
        ctk.CTkLabel(info_frame, text=title, font=("Microsoft YaHei UI", 12, "bold"), text_color="#333333", anchor="w").pack(fill="x")
        ctk.CTkLabel(info_frame, text=content, font=("Microsoft YaHei UI", 11), text_color="gray", anchor="w").pack(fill="x")
        
        # 删除按钮
        ctk.CTkButton(item, text="×", width=25, height=25, fg_color="#FF6B6B", hover_color="#FF5252", command=lambda: self.delete_lore_entry(index)).pack(side="right", padx=5)
        
        # 绑定点击编辑
        item.bind("<Double-Button-1>", lambda e: self.edit_lore_entry(index))
        for child in item.winfo_children():
            if not isinstance(child, ctk.CTkButton): # 排除按钮
                child.bind("<Double-Button-1>", lambda e: self.edit_lore_entry(index))

    def add_lore_entry(self):
        LorebookDialog(self.window, None, self.save_lore_entry)
        
    def edit_lore_entry(self, index):
        lorebook = self.cm.get("lorebook") or []
        if 0 <= index < len(lorebook):
            LorebookDialog(self.window, lorebook[index], lambda data: self.save_lore_entry(data, index))

    def save_lore_entry(self, data, index=None):
        lorebook = self.cm.get("lorebook") or []
        if index is not None:
            lorebook[index] = data
        else:
            lorebook.append(data)
        
        self.cm.set("lorebook", lorebook)
        self.refresh_lore_list()
        
    def delete_lore_entry(self, index):
        lorebook = self.cm.get("lorebook") or []
        if 0 <= index < len(lorebook):
            lorebook.pop(index)
            self.cm.set("lorebook", lorebook)
            self.refresh_lore_list()

    # --- 辅助方法 ---
    def create_card(self, parent, expand=False, pady=0):
        card = ctk.CTkFrame(parent, fg_color="white", corner_radius=15)
        card.pack(fill="both" if expand else "x", expand=expand, padx=5, pady=pady)
        
        # 内边距容器
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=15, pady=15)
        return inner

    def create_section_label(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=("Microsoft YaHei UI", 14, "bold"), text_color="#333333", anchor="w").pack(fill="x", pady=(0, 10))

    def create_input_row(self, parent, label, key, default_value, show=None):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=5)
        ctk.CTkLabel(frame, text=label, width=80, anchor="w", font=("Microsoft YaHei UI", 12), text_color="gray").pack(side="left")
        entry = ctk.CTkEntry(frame, show=show, border_width=0, fg_color="#F2F2F7", text_color="#333333")
        entry.insert(0, str(default_value))
        entry.pack(side="left", fill="x", expand=True, padx=5)
        self.entries[key] = entry

    def create_reminder_card(self, parent, key, title, reminders, label, default_val, entry_key):
        card = self.create_card(parent, pady=5)
        
        config = reminders.get(key, {})
        self.reminder_vars[f"{key}_enabled"] = ctk.BooleanVar(value=config.get("enabled", True))
        
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))
        ctk.CTkSwitch(header, text=title, variable=self.reminder_vars[f"{key}_enabled"], font=("Microsoft YaHei UI", 14, "bold"), progress_color="#7EA0B7").pack(anchor="w")
        
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="x")
        ctk.CTkLabel(content, text=label, text_color="gray", font=("Microsoft YaHei UI", 12)).pack(side="left", padx=(0, 10))
        entry = ctk.CTkEntry(content, width=150, border_width=0, fg_color="#F2F2F7")
        entry.insert(0, default_val)
        entry.pack(side="right", fill="x", expand=True)
        self.entries[entry_key] = entry

    def refresh_models(self):
        temp_cm = ConfigManager()
        temp_cm.config = self.cm.config.copy()
        temp_cm.set("api_base_url", self.entries["api_base_url"].get())
        temp_cm.set("api_key", self.entries["api_key"].get())
        temp_client = AIClient(temp_cm)
        try:
            models = temp_client.get_models()
            if models:
                self.model_combo.configure(values=models)
                self.model_combo.set(models[0])
                messagebox.showinfo("成功", f"获取到 {len(models)} 个模型")
            else:
                messagebox.showwarning("警告", "未能获取到模型")
        except Exception as e:
            messagebox.showerror("错误", f"刷新失败: {e}")

    def save_settings(self):
        import copy
        logging.info("=== save_settings called ===")
        
        try:
            # 使用深拷贝避免嵌套字典问题
            new_config = copy.deepcopy(self.cm.config)
            
            # 获取当前角色ID
            current_char_id = self.cm.get_current_character_id()
            logging.info(f"Current character ID: {current_char_id}")
            
            if not current_char_id or current_char_id not in new_config.get("characters", {}):
                logging.error("Current character not found!")
                messagebox.showerror("错误", "当前角色不存在")
                return
        except Exception as e:
            logging.error(f"Error in save_settings initialization: {e}")
            messagebox.showerror("错误", f"初始化失败: {str(e)}")
            return
        
        # 获取当前角色配置的引用
        char_config = new_config["characters"][current_char_id]
        
        # === 只保存已加载标签页的数据 ===
        
        # 保存"基础"标签页（API、天气、外观）
        if "基础" in self.tabs_loaded:
            try:
                logging.info("Saving 基础 tab settings...")
                new_config["api_base_url"] = self.entries["api_base_url"].get()
                new_config["api_key"] = self.entries["api_key"].get()
                new_config["model"] = self.model_combo.get()
        
                # 历史消息数量
                try:
                    max_history = int(self.entries["max_history_messages"].get())
                    if max_history < 0:
                        max_history = 0
                    elif max_history > 50:
                        max_history = 50
                    new_config["max_history_messages"] = max_history
                except:
                    new_config["max_history_messages"] = 10  # 使用默认值
                
                new_config["weather_city"] = self.entries.get("weather_city", ctk.CTkEntry(self.window)).get()
                new_config["weather_api_key"] = self.entries.get("weather_api_key", ctk.CTkEntry(self.window)).get()
                # 外观设置也在基础标签页
                # ... (外观设置代码保留在后面)
            except Exception as e:
                logging.error(f"Error saving 基础 tab: {e}")
                messagebox.showerror("错误", f"保存基础设置失败: {str(e)}")
                return
        
        # 保存"日常"标签页（工作时间）
        if "日常" in self.tabs_loaded:
            try:
                logging.info("Saving 日常 tab settings...")
                weekly_schedule = {}
                days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                for day in days:
                    weekly_schedule[day] = {
                        "enabled": self.schedule_entries[f"{day}_enabled"].get(),
                        "start": self.schedule_entries[f"{day}_start"].get(),
                        "end": self.schedule_entries[f"{day}_end"].get()
                    }
                char_config["weekly_schedule"] = weekly_schedule
            except Exception as e:
                logging.error(f"Error saving 日常 tab: {e}")
                # 不阻止保存，继续
        
        # 保存"提醒"标签页
        if "提醒" in self.tabs_loaded:
            try:
                logging.info("Saving 提醒 tab settings...")
                char_config["daily_target_cups"] = float(self.entries["daily_target_cups"].get())
                
                reminders = char_config.get("reminders", {})
                if "water" not in reminders:
                    reminders["water"] = {}
                reminders["water"]["enabled"] = True
                reminders["water"]["type"] = "interval"
                
                meal_times_str = self.entries["meal_times"].get()
                meal_times = [t.strip() for t in meal_times_str.split(",") if t.strip()]
                reminders["meal"] = {
                    "enabled": self.reminder_vars["meal_enabled"].get(),
                    "type": "fixed",
                    "times": meal_times,
                    "last_triggered": reminders.get("meal", {}).get("last_triggered")
                }
                
                sitting_interval = int(self.entries["sitting_interval"].get())
                reminders["sitting"] = {
                    "enabled": self.reminder_vars["sitting_enabled"].get(),
                    "type": "interval",
                    "interval": sitting_interval,
                    "last_triggered": reminders.get("sitting", {}).get("last_triggered")
                }
                
                relax_interval = int(self.entries["relax_interval"].get())
                reminders["relax"] = {
                    "enabled": self.reminder_vars["relax_enabled"].get(),
                    "type": "interval",
                    "interval": relax_interval,
                    "last_triggered": reminders.get("relax", {}).get("last_triggered")
                }
                
                char_config["reminders"] = reminders
                char_config["enable_random_chat"] = self.chat_var.get()
                char_config["random_chat_interval"] = int(self.entries["random_chat_interval"].get())
            except Exception as e:
                logging.error(f"Error saving 提醒 tab: {e}")
                messagebox.showerror("错误", f"保存提醒设置失败: {str(e)}")
                return
        
        # 保存"触摸"标签页
        if "触摸" in self.tabs_loaded:
            try:
                logging.info("Saving 触摸 tab settings...")
                touch_config = char_config.get("touch_areas", {"enabled": True, "areas": []})
                touch_config["enabled"] = self.touch_enabled_var.get()
                char_config["touch_areas"] = touch_config
            except Exception as e:
                logging.error(f"Error saving 触摸 tab: {e}")
        
        # 保存"角色"标签页（角色信息 + 表情）
        if "角色" in self.tabs_loaded:
            try:
                logging.info("Saving 角色 tab settings...")
                char_config["name"] = self.entry_char_name.get().strip() or "角色"
                char_config["persona"] = self.txt_persona.get("1.0", tk.END).strip()
                char_config["user_name"] = self.entry_user_name.get().strip() or "用户"
                char_config["user_identity"] = self.txt_user_identity.get("1.0", tk.END).strip()
            except Exception as e:
                logging.error(f"Error saving character info: {e}")
                messagebox.showerror("错误", f"保存角色信息失败: {str(e)}")
                return
        
        # 保存表情配置（角色配置）
        avatar_updated = False  # 标记是否更新了立绘
        
        if "角色" in self.tabs_loaded:
            try:
                expressions_config = char_config.get("expressions", {})
                
                # 处理默认立绘：如果用户选择了新立绘，复制到角色目录
                new_avatar_path = self.entry_default_img.get().strip()
                
                if new_avatar_path:
                    import shutil
                    logging.info(f"Processing avatar path: {new_avatar_path}")
                    logging.info(f"Is absolute path: {os.path.isabs(new_avatar_path)}")
                    logging.info(f"File exists: {os.path.exists(new_avatar_path)}")
                    
                    # 检查是否是绝对路径且文件存在
                    if os.path.isabs(new_avatar_path) and os.path.exists(new_avatar_path):
                        # 确保角色目录存在
                        char_dir = os.path.join("characters", current_char_id)
                        os.makedirs(char_dir, exist_ok=True)
                        
                        # 复制文件到角色目录
                        try:
                            _, ext = os.path.splitext(new_avatar_path)
                            avatar_dest = os.path.join(char_dir, f"character{ext}")
                            shutil.copy2(new_avatar_path, avatar_dest)
                            expressions_config["default"] = avatar_dest
                            char_config["avatar"] = avatar_dest  # 同步更新 avatar
                            avatar_updated = True
                            logging.info(f"✓ Copied avatar: {new_avatar_path} -> {avatar_dest}")
                        except Exception as e:
                            logging.error(f"Failed to copy avatar: {e}")
                            import traceback
                            logging.error(traceback.format_exc())
                            messagebox.showerror("错误", f"立绘文件复制失败: {str(e)}")
                            return
                    else:
                        # 如果是相对路径或不存在，直接使用（可能是已存在的路径）
                        logging.info(f"Using path as-is (relative or pre-existing): {new_avatar_path}")
                        expressions_config["default"] = new_avatar_path
                        char_config["avatar"] = new_avatar_path  # 同步更新 avatar
                
                expressions_config["restore_delay"] = int(self.entry_restore_delay.get())
                # mappings 已经在 save_expression_mapping 中实时更新了
                char_config["expressions"] = expressions_config
                logging.info(f"✓ Expression config saved, avatar_updated={avatar_updated}")
                
            except Exception as e:
                logging.error(f"Error saving expressions: {e}")
                import traceback
                logging.error(traceback.format_exc())
                messagebox.showerror("错误", f"保存表情设置失败: {str(e)}")
                return
        
        # 保存外观配置（角色配置） - 在"基础"标签页
        if "基础" in self.tabs_loaded:
            try:
                logging.info("Saving appearance settings...")
                appearance = char_config.get("appearance", {})
                
                font_type_var = self.entries.get("bubble_font_type")
                font_name_var = self.entries.get("bubble_font_name")
                font_file_entry = self.entries.get("bubble_font_file")
                
                font_type = font_type_var.get() if font_type_var else "custom"
                font_name = font_name_var.get() if font_name_var else "Microsoft YaHei UI"
                font_file = font_file_entry.get() if font_file_entry else ""
                
                logging.info(f"保存字体配置 - 类型: {font_type}, 名称: {font_name}, 文件: {font_file}")
                
                appearance["bubble"] = {
                    "background_color": self.entries.get("bubble_bg", ctk.CTkEntry(self.window)).get(),
                    "border_color": self.entries.get("bubble_border", ctk.CTkEntry(self.window)).get(),
                    "text_color": self.entries.get("bubble_text", ctk.CTkEntry(self.window)).get(),
                    "corner_radius": int(self.entries.get("bubble_corner", ctk.CTkSlider(self.window)).get()),
                    "padding_x": int(self.entries.get("bubble_padding_x", ctk.CTkSlider(self.window)).get()),
                    "padding_y": int(self.entries.get("bubble_padding_y", ctk.CTkSlider(self.window)).get()),
                    "font_size": int(self.entries.get("bubble_font", ctk.CTkSlider(self.window)).get()),
                    "border_width": int(self.entries.get("bubble_border_width", ctk.CTkSlider(self.window)).get()),
                    "font_type": font_type,
                    "font_name": font_name,
                    "font_file": font_file
                }
                appearance["input_box"] = {
                    "background_color": self.entries.get("input_bg", ctk.CTkEntry(self.window)).get(),
                    "border_color": self.entries.get("input_border", ctk.CTkEntry(self.window)).get(),
                    "text_color": self.entries.get("input_text", ctk.CTkEntry(self.window)).get(),
                    "button_color": self.entries.get("input_button", ctk.CTkEntry(self.window)).get(),
                    "button_hover_color": self.entries.get("input_button_hover", ctk.CTkEntry(self.window)).get(),
                    "corner_radius": int(self.entries.get("input_corner", ctk.CTkSlider(self.window)).get()),
                    "font_size": int(self.entries.get("input_font", ctk.CTkSlider(self.window)).get())
                }
                char_config["appearance"] = appearance
            except Exception as e:
                logging.error(f"Error saving appearance: {e}")
        
        # 将更新后的角色配置写回总配置
        new_config["characters"][current_char_id] = char_config
        
        try:
            logging.info("Saving config...")
            self.cm.save_config(new_config)
            
            # 重新加载配置（关键！确保内存中的config与文件一致）
            logging.info("Reloading config...")
            self.cm.config = self.cm.load_config()
            
            logging.info("Reloading AI client...")
            self.ai_client.reload_client()
            
            # 构建成功提示消息
            success_msg = "设置已保存！"
            if avatar_updated:
                success_msg += "\n\n✓ 立绘已更新并复制到角色目录"
                success_msg += "\n✓ 请重启程序以查看新立绘"
            else:
                success_msg += "\n\n字体更改将在下次显示气泡时生效。"
            
            logging.info(f"Showing success message: avatar_updated={avatar_updated}")
            messagebox.showinfo("保存成功", success_msg)
            
            if self.callback: 
                self.callback()
            self.window.destroy()
            
        except Exception as e:
            logging.error(f"Error in save_settings final stage: {e}")
            import traceback
            logging.error(traceback.format_exc())
            messagebox.showerror("保存失败", f"保存设置时出错:\n{str(e)}")
            return

class CharacterManagerWindow(ctk.CTkToplevel):
    """角色管理窗口"""
    def __init__(self, parent, config_manager, app):
        super().__init__(parent)
        self.cm = config_manager
        self.app = app  # 主应用引用
        self.title("角色管理")
        self.geometry("700x650")
        
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - 700) // 2
            y = (sh - 650) // 2
            self.geometry(f"+{x}+{y}")
        except:
            pass

        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))

        self.setup_ui()
        self.refresh_list()
        
    def setup_ui(self):
        # 顶部
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(header, text="角色管理", font=("Microsoft YaHei UI", 20, "bold")).pack(side="left")
        
        # 右侧按钮组
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right")
        
        ctk.CTkButton(btn_frame, text="导入角色", width=100, fg_color="#9C27B0", hover_color="#7B1FA2",
                     command=self.import_character).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="导入酒馆角色卡", width=120, fg_color="#FF9800", hover_color="#F57C00",
                     command=self.import_sillytavern_card).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="+ 新建角色", width=100, fg_color="#7EA0B7",
                     command=self.open_add_dialog).pack(side="left")
        
        # 说明
        info_frame = ctk.CTkFrame(self, fg_color="#E8F5E9", corner_radius=10)
        info_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(info_frame, text="提示：每个角色拥有独立的设定、聊天记录、健康数据等。切换角色时会生成告别和欢迎消息。", 
                    font=("Microsoft YaHei UI", 11), text_color="#2E7D32").pack(pady=10, padx=10)
        
        # 当前角色提示
        current_char_id = self.cm.get_current_character_id()
        current_char = self.cm.get_current_character()
        current_name = current_char.get("name", "未知") if current_char else "未知"
        
        current_frame = ctk.CTkFrame(self, fg_color="#FFF3E0", corner_radius=10)
        current_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(current_frame, text=f"当前角色：{current_name}", 
                    font=("Microsoft YaHei UI", 12, "bold"), text_color="#E65100").pack(pady=8, padx=10)
        
        # 列表区域
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="#F2F2F7", corner_radius=15)
        self.scroll.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        self.empty_label = ctk.CTkLabel(self.scroll, text="暂无角色\n点击右上角新建", text_color="gray")
        
    def refresh_list(self):
        # 清空列表
        for widget in self.scroll.winfo_children():
            widget.destroy()
            
        characters = self.cm.get_all_characters()
        current_char_id = self.cm.get_current_character_id()
        
        if not characters:
            self.empty_label.pack(pady=50)
            return
            
        for char_info in characters:
            self.create_item(char_info, is_current=(char_info["id"] == current_char_id))
            
    def create_item(self, char_info, is_current=False):
        card = ctk.CTkFrame(self.scroll, fg_color="white" if not is_current else "#E3F2FD", corner_radius=10)
        card.pack(fill="x", pady=5, padx=5)
        
        # 左侧信息
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=15, pady=10)
        
        # 角色名称
        name_text = char_info["name"]
        if is_current:
            name_text += " [当前]"
        ctk.CTkLabel(info, text=name_text, font=("Microsoft YaHei UI", 14, "bold"), 
                    text_color="#1976D2" if is_current else "#333333", anchor="w").pack(fill="x")
        
        # 角色ID
        sub_text = f"ID: {char_info['id']}"
        ctk.CTkLabel(info, text=sub_text, font=("Microsoft YaHei UI", 11), text_color="gray", anchor="w").pack(fill="x")
        
        # 右侧按钮
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=10)
        
        if not is_current:
            # 切换按钮
            ctk.CTkButton(btn_frame, text="切换", width=60, height=30, fg_color="#4CAF50", hover_color="#45A049", 
                          command=lambda: self.switch_character(char_info["id"])).pack(side="left", padx=5)
        
        # 导出按钮
        ctk.CTkButton(btn_frame, text="导出", width=60, height=30, fg_color="#9C27B0", hover_color="#7B1FA2",
                      command=lambda: self.export_character(char_info["id"])).pack(side="left", padx=5)
        
        # 编辑按钮
        ctk.CTkButton(btn_frame, text="编辑", width=60, height=30, fg_color="#2196F3", hover_color="#1976D2", 
                      command=lambda: self.edit_character(char_info["id"])).pack(side="left", padx=5)
        
        # 删除按钮（当前角色不能删除）
        if not is_current:
            ctk.CTkButton(btn_frame, text="×", width=30, height=30, fg_color="#FF6B6B", hover_color="#FF5252", 
                          command=lambda: self.delete_character(char_info["id"])).pack(side="left", padx=5)
                      
    def open_add_dialog(self):
        """打开新建角色对话框"""
        AddCharacterDialog(self, self.add_character)
        
    def add_character(self, name, persona, user_identity):
        """添加新角色"""
        char_id = self.cm.create_character(name, persona, user_identity)
        self.refresh_list()
        messagebox.showinfo("成功", f"角色 '{name}' 创建成功！")
    
    def edit_character(self, char_id):
        """编辑角色"""
        EditCharacterDialog(self, self.cm, char_id, self.refresh_list)
        
    def switch_character(self, char_id):
        """切换角色"""
        # 获取当前角色和目标角色信息
        current_char = self.cm.get_current_character()
        target_char = self.cm.config.get("characters", {}).get(char_id)
        
        if not target_char:
            messagebox.showerror("错误", "目标角色不存在")
            return
        
        # 确认切换
        if not messagebox.askyesno("确认切换", 
                                    f"确定要从 '{current_char.get('name')}' 切换到 '{target_char.get('name')}' 吗？\n\n切换后将生成告别和欢迎消息。"):
            return
        
        # 关闭窗口
        self.destroy()
        
        # 执行切换（在主线程中）
        self.app.perform_character_switch(char_id, current_char, target_char)
        
    def delete_character(self, char_id):
        """删除角色"""
        char_name = None
        for char in self.cm.get_all_characters():
            if char["id"] == char_id:
                char_name = char["name"]
                break
        
        if not char_name:
            return
        
        if messagebox.askyesno("确认删除", f"确定要删除角色 '{char_name}' 吗？\n\n此操作将删除该角色的所有数据（聊天记录、健康数据等），且无法恢复！"):
            success, msg = self.cm.delete_character(char_id)
            if success:
                self.refresh_list()
                messagebox.showinfo("成功", msg)
            else:
                messagebox.showerror("错误", msg)
    
    def export_character(self, char_id):
        """导出角色"""
        # 获取角色名称
        char_name = None
        for char in self.cm.get_all_characters():
            if char["id"] == char_id:
                char_name = char["name"]
                break
        
        if not char_name:
            return
        
        # 选择保存位置
        default_filename = f"{char_name}_角色包"
        file_path = filedialog.asksaveasfilename(
            title="导出角色",
            defaultextension=".zip",
            initialfile=default_filename,
            filetypes=[("ZIP文件", "*.zip"), ("所有文件", "*.*")]
        )
        
        if not file_path:
            return
        
        # 执行导出
        success, msg = self.cm.export_character(char_id, file_path)
        
        if success:
            messagebox.showinfo("导出成功", msg)
        else:
            messagebox.showerror("导出失败", msg)
    
    def import_character(self):
        """导入角色（ZIP格式）"""
        # 选择ZIP文件
        file_path = filedialog.askopenfilename(
            title="导入角色",
            filetypes=[("ZIP文件", "*.zip"), ("所有文件", "*.*")]
        )
        
        if not file_path:
            return
        
        # 执行导入
        success, msg, char_id = self.cm.import_character(file_path)
        
        if success:
            self.refresh_list()
            messagebox.showinfo("导入成功", msg)
        else:
            messagebox.showerror("导入失败", msg)
    
    def import_sillytavern_card(self):
        """导入 SillyTavern 角色卡（PNG格式）"""
        from utils import parse_sillytavern_card
        
        # 选择PNG文件
        file_path = filedialog.askopenfilename(
            title="选择 SillyTavern 角色卡",
            filetypes=[("PNG图片", "*.png"), ("所有文件", "*.*")]
        )
        
        if not file_path:
            return
        
        # 解析角色卡
        card_data = parse_sillytavern_card(file_path)
        
        if not card_data:
            messagebox.showerror("导入失败", "无法解析角色卡，请确保这是有效的 SillyTavern 角色卡 PNG 文件。")
            return
        
        # 提取信息
        name = card_data.get("name", "未命名角色")
        persona = card_data.get("persona", "")
        lorebook = card_data.get("lorebook", [])
        
        # 显示确认对话框
        confirm_msg = f"角色名称：{name}\n"
        confirm_msg += f"AI人设：{len(persona)} 字符\n"
        confirm_msg += f"Lorebook：{len(lorebook)} 个条目\n\n"
        confirm_msg += "确定要导入这个角色吗？"
        
        if not messagebox.askyesno("确认导入", confirm_msg):
            return
        
        try:
            # 创建角色专属目录（使用拼音命名）
            import shutil
            from utils import name_to_pinyin
            
            pinyin = name_to_pinyin(name)
            temp_char_id = f"char_{pinyin}"
            
            # 如果目录已存在，添加数字后缀
            counter = 1
            base_char_id = temp_char_id
            while os.path.exists(os.path.join("characters", temp_char_id)):
                temp_char_id = f"{base_char_id}{counter}"
                counter += 1
            
            char_dir = os.path.join("characters", temp_char_id)
            os.makedirs(char_dir, exist_ok=True)
            
            # 复制 PNG 到角色目录作为立绘
            avatar_dest = os.path.join(char_dir, "character.png")
            shutil.copy2(file_path, avatar_dest)
            
            # 创建角色
            char_id = self.cm.create_character(
                name=name,
                persona=persona,
                user_identity="",  # 默认为空，用户可以后续在设置中填写
                avatar=avatar_dest  # 使用复制后的文件路径
            )
            
            # 设置 Lorebook
            if lorebook:
                self.cm.update_character_config(char_id, "lorebook", lorebook)
            
            # 设置表情系统的 default 为这个立绘
            expressions_config = {
                "default": avatar_dest,
                "mappings": {},
                "restore_delay": 10
            }
            self.cm.update_character_config(char_id, "expressions", expressions_config)
            
            # 刷新列表
            self.refresh_list()
            
            success_msg = f"角色 '{name}' 导入成功！\n\n"
            success_msg += f"已导入 {len(lorebook)} 个 Lorebook 条目。\n"
            success_msg += "可以在「设置 → 角色」中查看和编辑。"
            
            messagebox.showinfo("导入成功", success_msg)
            
        except Exception as e:
            logging.error(f"Failed to create character from card: {e}")
            messagebox.showerror("导入失败", f"创建角色时出错：{str(e)}")


class AddCharacterDialog(ctk.CTkToplevel):
    """新建角色对话框"""
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.title("新建角色")
        self.geometry("500x400")
        
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - 500) // 2
            y = (sh - 400) // 2
            self.geometry(f"+{x}+{y}")
        except:
            pass
        
        self.attributes('-topmost', True)
        self.transient(parent)
        self.grab_set()
        
        self.setup_ui()
    
    def setup_ui(self):
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 角色名称
        ctk.CTkLabel(main_frame, text="角色名称", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        self.name_entry = ctk.CTkEntry(main_frame, placeholder_text="例如：梁俊杰", height=35)
        self.name_entry.pack(fill="x", pady=(0, 15))
        
        # AI人设
        ctk.CTkLabel(main_frame, text="AI人设（可选，稍后可在编辑中完善）", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        self.persona_text = ctk.CTkTextbox(main_frame, height=100)
        self.persona_text.pack(fill="x", pady=(0, 15))
        
        # 用户身份
        ctk.CTkLabel(main_frame, text="用户身份（可选）", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        self.user_identity_text = ctk.CTkTextbox(main_frame, height=60)
        self.user_identity_text.pack(fill="x", pady=(0, 20))
        
        # 按钮
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x")
        
        ctk.CTkButton(btn_frame, text="取消", width=100, fg_color="gray", command=self.destroy).pack(side="right", padx=5)
        ctk.CTkButton(btn_frame, text="创建", width=100, fg_color="#4CAF50", command=self.submit).pack(side="right")
    
    def submit(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror("错误", "请输入角色名称")
            return
        
        persona = self.persona_text.get("1.0", "end-1c").strip()
        user_identity = self.user_identity_text.get("1.0", "end-1c").strip()
        
        self.callback(name, persona, user_identity)
        self.destroy()


class EditCharacterDialog(ctk.CTkToplevel):
    """编辑角色对话框"""
    def __init__(self, parent, config_manager, char_id, refresh_callback):
        super().__init__(parent)
        self.cm = config_manager
        self.char_id = char_id
        self.refresh_callback = refresh_callback
        
        # 获取角色数据
        self.char_data = self.cm.config.get("characters", {}).get(char_id)
        if not self.char_data:
            messagebox.showerror("错误", "角色不存在")
            self.destroy()
            return
        
        self.title(f"编辑角色 - {self.char_data.get('name', '未知')}")
        self.geometry("600x500")
        
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - 600) // 2
            y = (sh - 500) // 2
            self.geometry(f"+{x}+{y}")
        except:
            pass
        
        self.attributes('-topmost', True)
        self.transient(parent)
        self.grab_set()
        
        self.setup_ui()
    
    def setup_ui(self):
        main_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 角色名称
        ctk.CTkLabel(main_frame, text="角色名称", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        self.name_entry = ctk.CTkEntry(main_frame, height=35)
        self.name_entry.insert(0, self.char_data.get("name", ""))
        self.name_entry.pack(fill="x", pady=(0, 15))
        
        # AI人设
        ctk.CTkLabel(main_frame, text="AI人设", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        self.persona_text = ctk.CTkTextbox(main_frame, height=150)
        self.persona_text.insert("1.0", self.char_data.get("persona", ""))
        self.persona_text.pack(fill="x", pady=(0, 15))
        
        # 用户姓名
        ctk.CTkLabel(main_frame, text="用户姓名", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        ctk.CTkLabel(main_frame, text="AI如何称呼用户", font=("Microsoft YaHei UI", 10), text_color="gray").pack(anchor="w", pady=(0, 5))
        self.user_name_entry = ctk.CTkEntry(main_frame, height=35, placeholder_text="例如：小明、月月、主人...")
        self.user_name_entry.insert(0, self.char_data.get("user_name", "用户"))
        self.user_name_entry.pack(fill="x", pady=(0, 15))
        
        # 用户身份
        ctk.CTkLabel(main_frame, text="用户身份", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        self.user_identity_text = ctk.CTkTextbox(main_frame, height=80)
        self.user_identity_text.insert("1.0", self.char_data.get("user_identity", ""))
        self.user_identity_text.pack(fill="x", pady=(0, 20))
        
        # 按钮
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x")
        
        ctk.CTkButton(btn_frame, text="取消", width=100, fg_color="gray", command=self.destroy).pack(side="right", padx=5)
        ctk.CTkButton(btn_frame, text="保存", width=100, fg_color="#4CAF50", command=self.submit).pack(side="right")
    
    def submit(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror("错误", "请输入角色名称")
            return
        
        persona = self.persona_text.get("1.0", "end-1c").strip()
        user_name = self.user_name_entry.get().strip() or "用户"
        user_identity = self.user_identity_text.get("1.0", "end-1c").strip()
        
        # 更新角色配置
        self.cm.update_character_config(self.char_id, "name", name)
        self.cm.update_character_config(self.char_id, "persona", persona)
        self.cm.update_character_config(self.char_id, "user_name", user_name)
        self.cm.update_character_config(self.char_id, "user_identity", user_identity)
        
        messagebox.showinfo("成功", "角色信息已更新")
        self.refresh_callback()
        self.destroy()


if __name__ == "__main__":
    setup_logging()
    root = tk.Tk()
    app = DesktopPetApp(root)
    root.mainloop()
