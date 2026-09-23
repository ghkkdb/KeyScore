# KeyScore Windows 打包流程

本文说明如何在 Windows 10/11 x64 环境中生成可直接运行的 KeyScore 测试版。项目统一使用根目录下的 `build_test.ps1`，输出为 PyInstaller `onedir` 目录，不生成单文件程序。

## 一、打包环境

建议使用项目现有的 64 位虚拟环境 `.venv64`。打包前确认以下文件存在：

```text
.venv64/Scripts/python.exe
src/keyscore/assets/KS.ico
data/profiles/
data/scores/
```

首次配置环境时执行：

```powershell
py -3.11 -m venv .venv64
.\.venv64\Scripts\python.exe -m pip install --upgrade pip
.\.venv64\Scripts\python.exe -m pip install -r requirements.txt
.\.venv64\Scripts\python.exe -m pip install "pyinstaller>=6,<7"
```

当前项目要求 Python 3.10 或更高版本，正式打包建议固定使用 Python 3.11 x64，避免不同开发机生成的运行库不一致。

## 二、打包前检查

先运行完整测试：

```powershell
$env:PYTHONPATH = "src"
.\.venv64\Scripts\python.exe -m unittest discover -s tests
```

确认测试全部通过后，检查需要随软件发布的内容：

- `data/scores` 中的示例曲谱是否正确；
- `data/profiles` 中的按键方案是否正确；
- `src/keyscore/assets/KS.ico` 是否为当前应用图标；
- `README.md`、曲谱制作说明和版本信息是否已更新。

打包脚本会把当前 `data/scores` 和 `data/profiles` 原样复制到发布目录，因此个人测试曲谱或不应公开的配置应在打包前移出这两个目录。

## 三、执行打包

在项目根目录打开 PowerShell，运行：

```powershell
.\build_test.ps1
```

脚本会自动完成以下工作：

1. 检查 `.venv64` 和 PyInstaller；
2. 清理上一轮 PyInstaller 构建缓存；
3. 使用 `main.py` 生成无控制台窗口的 Windows x64 程序；
4. 写入 `KS.ico` 应用图标；
5. 收集 PySide6 和 KeyScore 资源；
6. 复制曲谱与按键方案；
7. 删除未使用的 Qt 模块、插件、翻译和 ICU 文件，缩减体积。

成功后输出目录为：

```text
dist/KeyScore-Test/
├─ KeyScore-Test.exe
├─ data/
│  ├─ profiles/
│  └─ scores/
└─ _internal/
```

`KeyScore-Test.exe`、`data` 和 `_internal` 必须整体分发，不能只复制 EXE。

## 四、打包后验证

普通权限启动：

```powershell
.\dist\KeyScore-Test\KeyScore-Test.exe
```

至少完成以下检查：

1. 主窗口、图标和中文界面正常显示；
2. 曲谱列表和按键方案能够读取；
3. 新建、编辑和保存曲谱正常；
4. 普通权限记事本前台可以播放测试曲谱；
5. 管理员记事本作为目标时会弹出权限提示；
6. 同意 UAC 后 KeyScore 以管理员权限重启，并恢复当前曲谱与按键方案；
7. 取消权限提示后，再次播放仍会重新提示；
8. `F9` 播放/暂停、`F10` 急停及按键释放正常；
9. 关闭程序后没有残留的 KeyScore 进程。

管理员记事本可通过以下命令启动：

```powershell
Start-Process notepad.exe -Verb RunAs
```

## 五、生成分发压缩包

完成验证后，可将整个输出目录压缩：

```powershell
Compress-Archive `
    -Path ".\dist\KeyScore-Test\*" `
    -DestinationPath ".\dist\KeyScore-Test-win-x64.zip" `
    -Force
```

解压压缩包到一个全新的目录，再启动一次程序，确认没有依赖项目源码、虚拟环境或开发机上的临时文件。

## 六、常见问题

### 提示未安装 PyInstaller

```powershell
.\.venv64\Scripts\python.exe -m pip install "pyinstaller>=6,<7"
```

### Windows 显示未知发布者

当前测试版没有代码签名，UAC 和 SmartScreen 可能显示“未知发布者”。正式发布时应购买或配置可信的 Authenticode 代码签名证书，并对 EXE、安装包和更新程序签名。

### 只复制 EXE 后无法启动

当前使用 `onedir` 模式，依赖文件位于 `_internal`。必须分发完整的 `dist/KeyScore-Test` 目录。

### 管理员游戏前台按快捷键没有响应

普通权限程序无法可靠接收高权限窗口前台的快捷键。先在 KeyScore 中点击播放并切换到游戏，根据提示完成管理员重启；重启后双方权限一致，快捷键才可正常使用。

### 重新打包后仍出现旧内容

`build_test.ps1` 已启用 PyInstaller `--clean`。如果仍有旧文件，先确认启动的是当前项目下的 `dist/KeyScore-Test/KeyScore-Test.exe`，并检查是否存在另一个仍在运行的 KeyScore 实例。
