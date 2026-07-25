# DrinkingNow - Windows 健康提醒小工具

DrinkingNow 是一个常驻 Windows 系统托盘的健康提醒小工具，用来温柔地提醒喝水和久坐活动。程序以后台静默运行为主，提醒弹窗从屏幕右下角滑出，不打断当前工作。

## 功能

- 喝水提醒和久坐提醒独立计时
- 右下角毛玻璃风格提醒弹窗
- 系统托盘常驻水滴图标
- 提示音开关
- 暂停 1 小时、暂停 2 小时、直到手动恢复
- 暂停期间可随时恢复提醒
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
pyinstaller --onefile --windowed --icon=waterdrop.ico --name DrinkingNow main.py
```

打包完成后，成品位于：

```text
dist/DrinkingNow.exe
```

把这个 EXE 发给朋友即可使用，对方不需要安装 Python。

## 使用方式

1. 双击 `DrinkingNow.exe` 启动。
2. 首次启动会打开设置面板。
3. 设置喝水间隔、久坐间隔、提示音和开机自启后保存。
4. 程序会常驻右下角系统托盘。
5. 右键托盘图标可打开设置、暂停提醒、恢复提醒或退出。

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
  "first_run": false
}
```

## 项目结构

```text
DrinkingNow/
├── main.py
├── requirements.txt
├── README.md
├── waterdrop.ico
└── DrinkingNow.spec
```

## 依赖

- `pystray` - 系统托盘图标
- `Pillow` - 绘制水滴图标
- `tkinter` - 设置面板和提醒弹窗
- `winsound` - Windows 提示音
- `threading` - 后台计时器
- `json` - 本地配置

## 发布说明

源码仓库不提交 `build/`、`dist/`、`__pycache__/` 等生成文件。可执行文件 `DrinkingNow.exe` 通过 GitHub Release 附件发布。
