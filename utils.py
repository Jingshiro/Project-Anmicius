import os
import sys
import logging
import datetime
import urllib.request
import urllib.parse
import json
import re

def resource_path(relative_path):
    """
    获取资源文件的绝对路径
    PyInstaller打包后，资源文件会被解压到临时目录
    """
    try:
        # PyInstaller创建临时文件夹，将路径存储在_MEIPASS中
        base_path = sys._MEIPASS
    except Exception:
        # 如果不是打包环境，使用当前目录
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

def setup_logging(max_lines=800):
    """配置日志系统，并清理过大的日志文件"""
    log_file = 'debug.log'
    
    # 检查日志文件是否过大，如果超过指定行数则清理
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            # 如果超过最大行数，只保留最后max_lines行
            if len(lines) > max_lines:
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(f"# 日志已自动清理，保留最近{max_lines}条记录\n")
                    f.write(f"# 清理时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.writelines(lines[-max_lines:])
        except Exception as e:
            print(f"日志清理失败: {e}")
    
    # 配置日志
    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        encoding='utf-8'
    )

def name_to_pinyin(name):
    """将中文名称转换为拼音（用于生成角色ID）
    
    Args:
        name: 角色名称
        
    Returns:
        str: 拼音字符串（小写，无空格）
    """
    try:
        from pypinyin import lazy_pinyin, Style
        # 转换为拼音，无音调
        pinyin_list = lazy_pinyin(name, style=Style.NORMAL)
        # 拼接并转小写
        pinyin_str = ''.join(pinyin_list).lower()
        # 只保留字母和数字
        pinyin_str = re.sub(r'[^a-z0-9]', '', pinyin_str)
        # 限制长度（避免过长）
        if len(pinyin_str) > 20:
            pinyin_str = pinyin_str[:20]
        return pinyin_str if pinyin_str else "character"
    except ImportError:
        # 如果没有 pypinyin 库，使用 UUID 作为回退
        import uuid
        logging.warning("pypinyin not installed, using UUID for character ID")
        return str(uuid.uuid4())[:8]
    except Exception as e:
        # 任何异常都回退到 UUID
        import uuid
        logging.error(f"Failed to convert name to pinyin: {e}, using UUID")
        return str(uuid.uuid4())[:8]

def parse_sillytavern_card(png_path):
    """解析 SillyTavern 角色卡 PNG
    
    Args:
        png_path: PNG 文件路径
        
    Returns:
        dict: 包含 name, persona, lorebook 的字典，失败返回 None
    """
    import struct
    import base64
    
    try:
        with open(png_path, 'rb') as f:
            # 检查 PNG 签名
            signature = f.read(8)
            if signature != b'\x89PNG\r\n\x1a\n':
                logging.error("Not a valid PNG file")
                return None
            
            # 读取所有 chunks
            text_chunks = {}
            
            while True:
                length_data = f.read(4)
                if not length_data or len(length_data) < 4:
                    break
                
                length = struct.unpack('>I', length_data)[0]
                chunk_type = f.read(4).decode('ascii', errors='ignore')
                chunk_data = f.read(length)
                crc = f.read(4)
                
                # 只处理文本类型的 chunk
                if chunk_type in ['tEXt', 'iTXt', 'zTXt']:
                    null_index = chunk_data.find(b'\x00')
                    if null_index != -1:
                        keyword = chunk_data[:null_index].decode('latin-1')
                        text_data = chunk_data[null_index+1:]
                        
                        try:
                            text = text_data.decode('utf-8')
                            text_chunks[keyword] = text
                        except:
                            pass
                
                if chunk_type == 'IEND':
                    break
            
            # 尝试解码 chara 或 ccv3 字段
            for key in ['chara', 'ccv3']:
                if key in text_chunks:
                    try:
                        # Base64 解码
                        decoded = base64.b64decode(text_chunks[key])
                        json_str = decoded.decode('utf-8')
                        
                        # 解析 JSON
                        data = json.loads(json_str)
                        
                        # 提取基础信息
                        name = data.get("data", {}).get("name", data.get("name", "未命名角色"))
                        description = data.get("data", {}).get("description", data.get("description", ""))
                        
                        # 转换 Lorebook
                        lorebook = []
                        character_book = data.get("data", {}).get("character_book", {})
                        entries = character_book.get("entries", [])
                        
                        # 筛选 enabled=true 的条目
                        enabled_entries = [e for e in entries if e.get("enabled", False)]
                        
                        # 按 position 分组
                        before_char = []
                        after_char = []
                        others = []
                        
                        for entry in enabled_entries:
                            position = entry.get("position", "")
                            if position == "before_char":
                                before_char.append(entry)
                            elif position == "after_char":
                                after_char.append(entry)
                            else:
                                others.append(entry)
                        
                        # 排序：按 insertion_order
                        before_char.sort(key=lambda x: x.get("insertion_order", 0))
                        after_char.sort(key=lambda x: x.get("insertion_order", 0))
                        others.sort(key=lambda x: x.get("insertion_order", 0))
                        
                        # 合并
                        sorted_entries = before_char + after_char + others
                        
                        # 转换为 WaterAssistant 格式
                        for entry in sorted_entries:
                            constant = entry.get("constant", False)
                            keys = entry.get("keys", [])
                            content = entry.get("content", "")
                            
                            # 转换触发类型
                            if constant:
                                entry_type = "always"
                                keywords = ""
                            else:
                                entry_type = "keyword"
                                keywords = ", ".join(keys) if keys else ""
                            
                            # 如果是关键词触发但没有关键词，跳过
                            if entry_type == "keyword" and not keywords:
                                continue
                            
                            lorebook_entry = {
                                "id": str(entry.get("id", len(lorebook))),
                                "type": entry_type,
                                "keywords": keywords,
                                "content": content
                            }
                            
                            lorebook.append(lorebook_entry)
                        
                        logging.info(f"Parsed SillyTavern card: {name}, {len(lorebook)} lorebook entries")
                        
                        return {
                            "name": name,
                            "persona": description,
                            "lorebook": lorebook
                        }
                        
                    except Exception as e:
                        logging.error(f"Failed to decode {key}: {e}")
                        continue
            
            logging.error("No valid chara/ccv3 data found in PNG")
            return None
            
    except Exception as e:
        logging.error(f"Failed to parse SillyTavern card: {e}")
        return None

def get_weather_info(city=None, api_key=None):
    """获取天气信息
    
    Args:
        city: 城市名称 (中文/英文)，如果为None则自动根据IP定位
        api_key: 和风天气 API Key (可选)
        
    Returns:
        str: 天气描述
    """
    try:
        # 方案 A: 如果有 API Key，尝试使用和风天气 (QWeather)
        if api_key and city:
            # 1. 搜索城市 ID
            search_url = f"https://geoapi.qweather.com/v2/city/lookup?location={urllib.parse.quote(city)}&key={api_key}"
            with urllib.request.urlopen(search_url, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get("code") == "200" and data.get("location"):
                    city_id = data["location"][0]["id"]
                    
                    # 2. 获取实时天气
                    weather_url = f"https://devapi.qweather.com/v7/weather/now?location={city_id}&key={api_key}"
                    with urllib.request.urlopen(weather_url, timeout=5) as w_resp:
                        w_data = json.loads(w_resp.read().decode('utf-8'))
                        if w_data.get("code") == "200":
                            now = w_data["now"]
                            return f"{city} {now['text']} {now['temp']}°C"
                            
        # 方案 B: 使用 wttr.in (无需 Key)
        # 格式说明: %C=天气状况 %t=温度
        location = urllib.parse.quote(city) if city else ""
        url = f"https://wttr.in/{location}?format=%C+%t&lang=zh"
        
        # 模拟浏览器 User-Agent，防止被 403
        req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0'})
        
        with urllib.request.urlopen(req, timeout=10) as response:
            weather_text = response.read().decode('utf-8').strip()
            # 清理可能的 HTML 标签（wttr.in 有时会返回 HTML）
            if "<" in weather_text: 
                return "天气数据获取异常"
            
            # 如果没有指定城市，尝试从响应中解析（wttr.in 有时会包含地点）
            prefix = f"{city} " if city else ""
            return f"{prefix}{weather_text}"
            
    except Exception as e:
        logging.error(f"Weather API failed: {e}")
        return "天气未知"

def get_weather_info(city, api_key=None):
    """获取天气信息
    
    Args:
        city: 城市名称 (中文/英文)
        api_key: 和风天气 API Key (可选)
        
    Returns:
        str: 天气描述
    """
    if not city:
        return "未知"
        
    try:
        # 方案 A: 如果有 API Key，尝试使用和风天气 (QWeather)
        if api_key:
            # 1. 搜索城市 ID
            search_url = f"https://geoapi.qweather.com/v2/city/lookup?location={urllib.parse.quote(city)}&key={api_key}"
            with urllib.request.urlopen(search_url, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get("code") == "200" and data.get("location"):
                    city_id = data["location"][0]["id"]
                    
                    # 2. 获取实时天气
                    weather_url = f"https://devapi.qweather.com/v7/weather/now?location={city_id}&key={api_key}"
                    with urllib.request.urlopen(weather_url, timeout=5) as w_resp:
                        w_data = json.loads(w_resp.read().decode('utf-8'))
                        if w_data.get("code") == "200":
                            now = w_data["now"]
                            return f"{city} {now['text']} {now['temp']}°C"
                            
        # 方案 B: 使用 wttr.in (无需 Key)
        # 使用 format=j1 获取 JSON 格式更稳定，或者直接获取简单文本
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=%C+%t&lang=zh"
        # 模拟浏览器 User-Agent，防止被 403
        req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0'})
        
        with urllib.request.urlopen(req, timeout=10) as response:
            weather_text = response.read().decode('utf-8').strip()
            # 清理可能的 HTML 标签（wttr.in 有时会返回 HTML）
            if "<" in weather_text: 
                return f"{city} 天气数据获取异常"
            return f"{city} {weather_text}"
            
    except Exception as e:
        logging.error(f"Weather API failed: {e}")
        return f"{city} 天气未知"
