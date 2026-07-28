# DrinkingNow — Windows 健康提醒小工具

DrinkingNow 是一个常驻 Windows 系统托盘的健康提醒小工具，温柔地提醒喝水和久坐活动。程序后台静默运行，提醒弹窗从屏幕右下角滑出，不打断当前工作。

## 功能

- 喝水提醒和久坐提醒独立计时，间隔可分别设置（最少 5 分钟）
- 右下角毛玻璃风格提醒弹窗，8 秒自动消失
- **强制模式**：开启后弹窗不点按钮不消失（喝水/久坐独立开关）
- 两提醒同时触发时**自动替换**，不会互相卡死
- **左键点击托盘图标** → 打开设置面板
- **右键点击托盘图标** → 暂停提醒 / 退出
- 系统托盘水滴图标，灰色（暂停）/ 蓝色（正常）/ 亮蓝（提醒中）三种状态
- 提示音开关
- 暂停 1 小时、暂停 2 小时、直到手动恢复，暂停期间可随时恢复
- 6 种主题颜色（蓝 / 绿 / 灰 / 深灰 / 紫 / 橙）
- 开机自启
- 单实例运行，重复打开不会生成多个托盘图标

## 运行环境

- Windows 10 / 11
- Python 3.10+

## 从源码运行

```bash
pip install -r requirements.txt
python main.py
```

如果不想出现命令行窗口，可以使用 `pythonw.exe` 启动。

## 打包为 EXE

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --noupx --icon=waterdrop.ico --add-data "waterdrop.ico;." --name DrinkingNow main.py
```

打包完成后，成品位于：

```text
dist/DrinkingNow.exe
```

> 建议加 `--noupx` 减少误报；用 `--add-data` 将图标嵌入 exe，确保运行时任务栏显示水滴图标。

## 使用方式

1. 下载 `DrinkingNow.exe` 双击启动
2. 首次启动自动打开设置面板
3. 设置喝水间隔、久坐间隔、提示音、强制模式、开机自启等，保存
4. 程序常驻右下角系统托盘，显示水滴图标
5. **左键**托盘图标 → 打开设置面板；**右键**托盘图标 → 暂停提醒 / 退出

## 配置文件

用户设置保存在：

```text
C:\Users\<用户名>\.drinkingnow\settings.json
```

示例：

```json
{
  "water_interval": 30,
  "sedentary_interval": 45,
  "sound_enabled": true,
  "autostart": false,
  "first_run": false,
  "theme": "blue",
  "force_water": false,
  "force_sedentary": false
}
```

## 项目结构

```text
DrinkingNow/
├── main.py
├── requirements.txt
├── README.md
├── waterdrop.ico
├── DrinkingNow.spec
└── .gitignore
```

## 依赖

- [`pystray`](https://github.com/moses-palmer/pystray) — 系统托盘图标
- [`Pillow`](https://python-pillow.org/) — 绘制水滴图标
- `tkinter` — 设置面板和提醒弹窗
- `winsound` — Windows 提示音

## 许可

MIT License

## 发布说明

源码仓库不提交 `build/`、`dist/`、`__pycache__/` 等生成文件。可执行文件通过 [GitHub Release](https://github.com/luoyongjun944-eng/DrinkingNow/releases) 附件发布。
