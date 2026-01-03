import PyInstaller.__main__
import os
import json

print("Building Project Anmicius...")

# 创建默认配置（不含任何用户数据）
default_config = {
    "name": "默认助手",
    "persona": "你是一个友善的AI桌面助手，会提醒用户注意健康。你的回复简短、温暖、贴心。"
}

with open("default_config.json", "w", encoding="utf-8") as f:
    json.dump(default_config, f, ensure_ascii=False, indent=4)

# 创建默认立绘（如果不存在）
if not os.path.exists("default_character.png"):
    from PIL import Image, ImageDraw
    img = Image.new('RGBA', (400, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 绘制简单的圆形头像
    draw.ellipse([50, 50, 350, 350], fill=(135, 206, 235, 255), outline=(70, 130, 180, 255), width=5)
    # 眼睛
    draw.ellipse([120, 140, 160, 180], fill=(255, 255, 255, 255))
    draw.ellipse([240, 140, 280, 180], fill=(255, 255, 255, 255))
    draw.ellipse([130, 150, 150, 170], fill=(0, 0, 0, 255))
    draw.ellipse([250, 150, 270, 170], fill=(0, 0, 0, 255))
    # 嘴巴
    draw.arc([140, 200, 260, 280], 0, 180, fill=(70, 130, 180, 255), width=5)
    img.save("default_character.png")
    print("Generated default_character.png")

# 检查资源文件（将 default_character.png 以 character.png 的名字打包）
add_data_args = []

# 特殊处理：default_character.png 打包时重命名为 character.png
if os.path.exists("default_character.png"):
    # PyInstaller 的 --add-data 格式：源文件;目标目录
    # 但不支持重命名，所以我们临时创建一个 character.png
    import shutil
    shutil.copy2("default_character.png", "character.png")
    add_data_args.extend(["--add-data", "character.png;."])
    print("Will pack default_character.png as character.png")

for file_name in ["icon.png", "prompt_templates.json", "ChillRoundFRegular.ttf"]:
    if os.path.exists(file_name):
        add_data_args.extend(["--add-data", f"{file_name};."])

# 图标参数
icon_args = ["--icon=icon.png"] if os.path.exists("icon.png") else []

# 打包参数
args = [
    "main.py",
    "--name=ProjectAnmicius",
    "--onefile",
    "--noconsole",
    "--clean",
    "--noconfirm",
] + icon_args + add_data_args

# 隐藏导入
for imp in ["pypinyin", "pystray", "PIL", "PIL._tkinter_finder", "customtkinter"]:
    args.extend(["--hidden-import", imp])

PyInstaller.__main__.run(args)

# 清理临时文件
if os.path.exists("default_config.json"):
    os.remove("default_config.json")
# 清理打包时临时创建的 character.png
if os.path.exists("character.png") and os.path.exists("default_character.png"):
    # 只有当 default_character.png 存在时才删除 character.png（说明是我们临时创建的）
    os.remove("character.png")

print("\nBuild completed: dist/ProjectAnmicius.exe")
