# stm32-rtt · STM32CubeMX CMake RTT Installer

给 **STM32CubeMX 生成的 CMake 项目**添加 SEGGER RTT。一行启动，交互安装；参数齐全，Agent 无需应答。

[安装页面与命令生成器](https://guajun.github.io/stm32-rtt/) · [Release 下载](https://github.com/guajun/stm32-rtt/releases/latest) · [CI](https://github.com/guajun/stm32-rtt/actions/workflows/ci.yml)

> **不要用 `Middlewares` 做 RTT 文件夹名字！该目录由 CubeMX 管理。** 安装器会拒绝 `Middlewares`（不区分大小写），也会保护 `Core`、`Drivers`、`cmake`、`build` 等目录。推荐 `SEGGER_RTT` 或 `DebugRTT`。

## 前置条件

- **安装器运行时**：Python **3.8+** 和 Git 在 PATH 中；Python 无第三方依赖。Windows 也支持 `py -3`。Python 执行安装逻辑，Git 获取上游代码。
- **启动入口**：Windows PowerShell **5.1+** / PowerShell 7，或 POSIX Shell（Linux / macOS / Git Bash）。POSIX 一行下载命令还需要 `curl`；已下载的本地脚本无需 curl。Windows 一行命令使用 PowerShell 内置的 `Invoke-RestMethod`。
- 项目包含顶层 `CMakeLists.txt` 和 `cmake/stm32cubemx/CMakeLists.txt`。
- submodule 模式：项目目录须为 Git 仓库根目录，至少有一次提交，`.gitmodules` 无待提交改动。
- 安装阶段需要能访问 SEGGER 官方 Git 仓库；安装完成后构建无需联网。

| v1.0.0 安装模式 | 需要 Git 命令 | 项目需要是 Git 仓库 | 支持的版本选择 |
| --- | --- | --- | --- |
| `submodule` | 是，获取代码并注册 submodule | 是，仓库根目录且已有提交 | tag / 完整 commit SHA / latest；最终固定为 commit |
| `source` 纯源码 | **是，目前通过 git clone 获取代码后复制源码** | **否** | tag / 完整 commit SHA / latest；最终记录实际 commit |

**不创建 submodule，并不等于当前安装器不需要 Git。** v1.0.0 的纯源码模式不要求项目有 `.git`，安装完成的 RTT 目录也没有 Git 元数据，但获取源码时仍会调用 Git。当前尚未实现直接下载源码 ZIP、Release 附件或从本地包导入。

Python 和 Git 是本工具安装阶段的依赖；RTT 固件运行及后续构建不依赖本安装器的 Python。后续固件构建仍需要项目原有的 CMake、构建工具和 ARM 工具链，安装器本身不会调用它们。

## 一行安装

先切换到你的 CubeMX CMake 项目目录。不传参数时会交互询问项目、RTT 版本、文件夹、模式和可选 CMake target。

**Windows PowerShell（5.1 / 7）**

```powershell
& ([scriptblock]::Create((Invoke-RestMethod 'https://github.com/guajun/stm32-rtt/releases/latest/download/install.ps1')))
```

**POSIX Shell**

```sh
curl -fsSL https://github.com/guajun/stm32-rtt/releases/latest/download/install.sh | sh
```

## Agent / 非交互式

**传入任何参数后默认不再提问**，未提供的选项采用默认值。`-NonInteractive` / `--non-interactive` 可以显式使用全部默认值。失败返回非零退出码；成功输出摘要及最后一行 JSON。为可复现安装，固定安装器 Release URL 和 RTT tag / commit。

```powershell
& ([scriptblock]::Create((Invoke-RestMethod 'https://github.com/guajun/stm32-rtt/releases/download/v1.0.0/install.ps1'))) -Project 'C:\firmware\my-board' -Version 'V8.58.0' -Directory 'SEGGER_RTT' -Mode submodule -NonInteractive
```

```sh
curl -fsSL https://github.com/guajun/stm32-rtt/releases/download/v1.0.0/install.sh | sh -s -- --project '/path/to/my-board' --version V8.58.0 --directory SEGGER_RTT --mode source --non-interactive
```

| PowerShell | POSIX Shell | 默认值 / 说明 |
| --- | --- | --- |
| `-Project` | `--project` | 当前目录；支持空格和中文路径 |
| `-Version` | `--version` | `latest`：最新数字 release tag；也可指定 tag 或完整 40 位 SHA |
| `-Directory` | `--directory` | `SEGGER_RTT`；单级目录，字母/数字/下划线/连字符，最长 64 字符 |
| `-Mode` | `--mode` | `submodule` 或 `source`，默认 `submodule` |
| `-Target` | `--target` | 默认 `${CMAKE_PROJECT_NAME}`；自定义可执行目标时显式指定 |
| `-NonInteractive` | `--non-interactive` | 不提问，使用默认值或传入参数 |
| `-ListVersions` | `--list-versions` | 联网列出上游 tags 后退出 |
| `-Repository` | `--repository` | 默认 `https://github.com/SEGGERMicro/RTT.git`；可指定可信 Git 镜像 |
| `-Help` | `--help` | 参数说明 |

列出可选 RTT 版本：

```powershell
& ([scriptblock]::Create((Invoke-RestMethod 'https://github.com/guajun/stm32-rtt/releases/latest/download/install.ps1'))) -ListVersions
```

```sh
curl -fsSL https://github.com/guajun/stm32-rtt/releases/latest/download/install.sh | sh -s -- --list-versions
```

## 两种模式

- **submodule**：保留官方仓库来源和固定 commit，方便后续管理。会暂存 `.gitmodules` 与 RTT gitlink；请检查后把所有安装文件一起提交。其他文件已有的暂存状态保留。别人克隆项目时用 `git clone --recurse-submodules`，或运行 `git submodule update --init --recursive`。
- **source**：通过 Git 获取所选版本，复制全部源码（含许可证）并移除 Git 元数据。机器仍须安装 Git，但目标项目无需初始化 Git。适合交付源码、离线构建与不希望管理 submodule 的项目。与 submodule 一样，可指定 tag 或完整 commit，并不限于 tag。

## 安装会改什么

```text
<project>/
├── SEGGER_RTT/                 # 或选择的目录；官方完整源码
├── cmake/segger-rtt.cmake       # RTT sources / includes
├── .stm32-rtt.json             # 选项、解析后的 tag / commit、文件 SHA256
└── CMakeLists.txt              # 末尾添加带 BEGIN/END 标记的 include
```

接入 `RTT/SEGGER_RTT.c`、`RTT/SEGGER_RTT_printf.c`，并添加 `RTT` 与 `Config` include 路径。不修改 CubeMX 生成的 `cmake/stm32cubemx`，不修改应用源代码，不添加 syscall retargeting 或汇编优化文件。

在应用的 CubeMX `USER CODE` 区域使用：

```c
#include "SEGGER_RTT.h"

SEGGER_RTT_WriteString(0, "Hello from STM32!\n");
SEGGER_RTT_printf(0, "counter=%u\n", counter);
```

重新 CMake configure / build，再通过 J-Link RTT Viewer 等工具查看输出。硬件与调试器配置参见 [SEGGER RTT 文档](https://kb.segger.com/RTT)。

## 重复运行、升级和移除

相同参数重复运行会验证已安装文件哈希、CMake 接入与 submodule commit，成功后不重复修改。`latest` 在第一次安装时固定为实际 commit；再次运行不会自动升级。配置不同、文件被修改、目录已存在或顶层 CMake 有手工 RTT 接入时会报错，供你审阅。

当前版本不提供原地升级或自动卸载。需要换版本/模式/目录时，请先提交或备份项目，然后审阅移除本工具的 CMake BEGIN/END 区块、`cmake/segger-rtt.cmake`、`.stm32-rtt.json` 与 RTT 目录；submodule 还应按 Git submodule 流程移除其注册与元数据，再重新安装。不会自动迁移现有手工 RTT 接入。

普通安装异常会尝试回滚本次修改；进程被强制终止、断电或磁盘无法写入仍需通过 Git 检查恢复。配置文件默认来自上游 `Config/SEGGER_RTT_Conf.h`；如需项目自定义 RTT 配置，请参考上游建议，将配置复制到项目自己的配置目录并调整 include 路径。

## 下载校验与离线启动

Release 提供独立的 `install.ps1`、`install.sh` 和 `SHA256SUMS`。两个脚本均内嵌同一安装核心，无需在运行时下载其他工具文件。可以先下载、审阅、校验，再运行；仍需访问上游 Git 或通过 `--repository` 提供本地镜像。

```sh
sha256sum -c SHA256SUMS
sh install.sh --project /path/to/project --mode source --version V8.58.0
```

```powershell
Get-FileHash .\install.ps1 -Algorithm SHA256
.\install.ps1 -Project 'C:\firmware\my-board' -Mode source -Version V8.58.0
```

## 开发和发布

```sh
python tools/build.py
python -m unittest discover -s tests -v
```

`src/installer.py` 为唯一安装逻辑；`tools/build.py` 生成自包含脚本与校验和。CI 在 Windows / Linux / macOS 上测试，Windows 额外检查 PowerShell 5.1。测试采用本地模拟上游，包含实际 Git submodule 与脚本入口测试。

维护者创建并推送版本 tag 后，可通过 `gh workflow run release.yml -f tag=v1.0.1` 构建、测试并发布 Release；也可本地构建后 `gh release create v1.0.1 dist/install.ps1 dist/install.sh dist/SHA256SUMS --verify-tag --generate-notes`。Pages 直接部署 `main` 分支的 `docs/`。

工具自身为 MIT 许可；SEGGER RTT 保留其[官方许可证](https://github.com/SEGGERMicro/RTT/blob/main/LICENSE.md)。本项目不隶属于 ST 或 SEGGER。
