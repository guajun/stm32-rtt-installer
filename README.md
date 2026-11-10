# stm32-rtt-installer · STM32CubeMX CMake RTT Installer

给 STM32CubeMX CMake 工程一键接入 SEGGER RTT。自动接入源文件与 include 路径，保护 CubeMX 管理目录；支持幂等检查、固定来源和 Agent 非交互模式。默认复制源码，无需 Git。

**此分支为 v1.1 预览，尚未发布正式 Release。** PR 的 Pages 预览同时提供本分支脚本；以下示例采用本地构建。公开 `releases/latest` 仍为 v1.0，不能用于测试新增压缩包功能。

> **不要使用 Middlewares 作为文件夹名，该目录由 CubeMX 管理。** 安装器也会拒绝 Core、Drivers、cmake、build 等受保护名称。推荐 SEGGER_RTT 或 DebugRTT。

## 推荐流程

主页面只选择项目路径、安装方式和版本，默认复制源码。高级 / 离线安装区域保留 pack、ZIP、本地文件、HTTPS URL、SHA256、目录和 CMake target。

```sh
# 官方最新正式发布版，解析为具体 tag / commit 后下载官方源码 ZIP
sh dist/install.sh --project /path/to/board --mode source --version release
# main 最新源码快照，安装时解析并固定 commit
sh dist/install.sh --project /path/to/board --mode source --version main
# 指定版本 / ref；submodule 也支持这些版本选择
sh dist/install.sh --project /path/to/board --mode submodule --version V8.58.0
```

PowerShell 使用 `-Project`、`-Mode`、`-Version` 对应参数。`release` 和 `main` 是不同策略：main 可能包含尚未发布的修复。2026-11-10 核对时，main 为 `9106eaa39babe53e00994d7828c1afb29390cdc1`，包含 GetBytesInBuffer 修复；正式 V8.58.0 为 `4d8feab3150f86f37a9d323ddc88d6cdf5673072`。这些 SHA 仅为核对记录，安装器实时解析实际来源，不写死快照。

成功后 `.stm32-rtt.json` 记录请求版本、解析版本、具体 commit 和文件哈希。重复执行相同参数只验证已有安装，不会随 main 移动而隐式更新。需要换版本时先审阅移除旧接入。`latest` 保留已有 CLI 的数字 tag 语义（pack 为最新正式 Release），不将它当作 main；主页面明确使用 release / main，避免混淆。CLI 未指定版本仍保留 latest 的兼容默认值；不传任何参数的交互流程推荐 release。

页面只生成命令，不在浏览器内拉取版本列表，不需要共享版本目录或额外后端。普通在线复制使用官方 GitHub 源码 ZIP；格式与下载地址是高级选项。

## 安装方式与运行依赖

| 模式 | RTT 格式与来源 | Git 命令 / Git 项目 | 网络 |
| --- | --- | --- | --- |
| submodule | 上游仓库或 Git 镜像 | 都需要；项目为仓库根目录且已有提交 | 获取代码时需要 |
| source + pack | 官方 Release、HTTPS URL、本地 .pack | **都不需要** | 本地文件安装不联网 |
| source + github-zip | 官方 tag/commit 快照、HTTPS URL、本地 ZIP | **都不需要** | 本地文件安装不联网 |

- 所有模式需 **Python 3.8+**，无第三方 Python 包依赖。ZIP/pack 用标准库解压，无需 7-Zip、WinRAR、unzip 或 CMSIS Pack 管理器。
- Windows：PowerShell **5.1+** / 7；Python 支持 py -3 或 PATH 上的 python3/python。
- POSIX：sh + python3/python；在线一行下载另需 curl，运行本地脚本无需 curl。
- 本地包不查询版本、不访问 GitHub、不调用 Git。指定 HTTPS URL 时仅下载该 URL；官方自动来源使用 GitHub HTTP API，受 GitHub API 访问限制影响。
- Python 是安装阶段依赖，固件不需要 Python；后续构建仍需项目原有 CMake、构建工具和 ARM 工具链。
- 项目必须包含 CMakeLists.txt 和 cmake/stm32cubemx/CMakeLists.txt。

非 submodule **只接受 .pack 和源码 ZIP 文件**，不支持本地目录、tar.gz、7z、RAR。压缩方式支持 ZIP Stored / Deflate。

## 本地构建与交互

```sh
python tools/build.py
```

```powershell
.\dist\install.ps1
```

```sh
sh dist/install.sh
```

不传参数只询问项目、安装方式和版本，默认 source / release。高级和离线场景通过现有 CLI 参数指定；本地包不查询在线版本或联网。

## 非交互示例

传入任何参数后默认不提问。PowerShell 参数与 Shell 参数对应见下表。



```powershell
# 官方 Release pack，无需 Git
.\dist\install.ps1 -Project 'C:\firmware\board' -Mode source -Format pack -Version V8.58.0
# GitHub 源码 ZIP，无需 Git，tag 先解析成 commit
.\dist\install.ps1 -Project 'C:\firmware\board' -Mode source -Format github-zip -Version V8.58.0
# 本地包，完全离线；扩展名推断格式，并自动使用 source
.\dist\install.ps1 -Project 'C:\firmware\board' -Archive 'C:\downloads\SEGGER.RTT.8.58.0.pack'
.\dist\install.ps1 -Project 'C:\firmware\board' -Archive 'C:\downloads\RTT-8.58.0.zip'
```

```sh
# 官方在线来源
sh dist/install.sh --project /path/to/board --mode source --format pack --version V8.58.0
sh dist/install.sh --project /path/to/board --mode source --format github-zip --version V8.58.0
# 本地包
sh dist/install.sh --project /path/to/board --archive '/downloads/SEGGER.RTT.8.58.0.pack'
sh dist/install.sh --project /path/to/board --archive '/downloads/RTT-8.58.0.zip'
# 任意来源的 HTTPS pack/ZIP；来源不改变格式处理方式
sh dist/install.sh --project /path/to/board --format pack --archive 'https://github.com/SEGGERMicro/RTT/releases/download/V8.58.0/SEGGER.RTT.8.58.0.pack'
# 可选压缩包校验
sh dist/install.sh --project /path/to/board --archive '/downloads/RTT.zip' --sha256 '<64位SHA256>'
# Git submodule
sh dist/install.sh --project /path/to/board --mode submodule --version V8.58.0
```

## 参数

| PowerShell | POSIX | 说明 |
| --- | --- | --- |
| -Project | --project | 默认当前目录；支持空格和中文路径 |
| -Mode | --mode | submodule / source；默认 source；submodule 需显式选择 |
| -Format | --format | pack / github-zip；source 默认 github-zip，archive 为 .pack 时自动推断 pack |
| -Archive | --archive | 本地 .pack/.zip 文件或 HTTPS URL；优先于官方下载，不支持目录 |
| -Sha256 | --sha256 | 可选压缩包 SHA256，错误时不修改项目 |
| -Version | --version | release 正式版 / main 源码快照 / tag、ref、完整commit；latest 保留原语义 |
| -Directory | --directory | 默认 SEGGER_RTT；单级目录，64字符内，字母/数字/下划线/连字符 |
| -Target | --target | 默认 ${CMAKE_PROJECT_NAME}，可指定 executable target |
| -Repository | --repository | 默认 SEGGER 官方；在线 source 支持 GitHub 仓库，submodule 支持 Git 镜像 |
| -NonInteractive | --non-interactive | 不提问 |
| -ListVersions | --list-versions | 查询 tag 后退出；source 使用 HTTP API，无需 Git；不能与 archive 合用 |
| -Help | --help | 参数说明 |

显式 archive 不访问 GitHub API，version 仅作为可选标签记录，默认 local / external，**不声称本地包对应某个 commit**。安装清单记录压缩包来源、SHA256 和安装文件哈希；官方在线 ZIP 记录解析后的 commit，pack 不伪造 commit。

## 压缩包结构

接受根目录直接包含 RTT/、Config/、LICENSE.md 的包，或多一层目录的 GitHub ZIP。pack 还需同级 .pdsc 描述文件。多个 RTT 根目录、缺文件或嵌套过深会拒绝。

```text
官方 pack                    GitHub 源码 ZIP
├── RTT/                     └── RTT-8.58.0/
├── Config/                      ├── RTT/
├── LICENSE.md                   ├── Config/
└── SEGGER.RTT.pdsc               └── LICENSE.md 等
```

统一复制识别出的源码根目录，保留许可证及该根目录其他文件，不依赖外层目录名。会校验条目路径、大小、数量、符号链接、加密与重复条目。

## 项目改动与重复执行

添加 RTT 目录、cmake/segger-rtt.cmake、.stm32-rtt.json，并在顶层 CMake 末尾追加 BEGIN/END include。接入 RTT 核心、printf、RTT 与 Config include；不修改 CubeMX 的 cmake/stm32cubemx，不自动 retarget libc printf。

```c
#include "SEGGER_RTT.h"
SEGGER_RTT_WriteString(0, "Hello STM32!\n");
SEGGER_RTT_printf(0, "counter=%u\n", counter);
```

相同参数重复执行会验证已有安装；本地包变更也会报错。已安装在线来源不重复下载，latest 不会隐式升级。不同选项、已有目录、手工 RTT 接入或 v1.0 source 安装不自动迁移，请先备份并审阅移除旧接入再安装。

submodule 暂存 .gitmodules 与 gitlink，请连同安装文件审阅提交。普通异常尝试回滚；强制终止或磁盘不可写需检查恢复。不提供自动升级/卸载。

## 验证

```sh
python tools/build.py
python -m unittest discover -s tests -v
node --test tests/test_page.cjs
```

CI 在 Windows / Linux / macOS 测试，覆盖无 Git/无网络本地安装、HTTP 下载、格式与根目录、恶意路径、回滚和脚本入口。Windows 额外检查 PowerShell 5.1。PR 预览不替换正式 Release。

真实 CubeMX 工程的 Windows / WSL 测试使用 `tools/test_project.py`，覆盖原有 8 个场景及 release/main × 复制/submodule 的 Debug/Release，包含实际 RTT 调用与 ELF 符号检查。工程只复制到新的工作目录，原工程不会修改。参见 [Windows / WSL 端到端报告](docs/testing/windows-wsl-e2e.md)。用户的本地测试工程不随仓库分发。

维护者可在提交并推送 PR head 后运行 `python tools/publish_preview.py --pr <编号> --work-dir <已有临时工作目录>`，发布 `/pr/<编号>/` 的页面与独立脚本。发布工具保留 main 文档作为主站、保留其他 PR 预览，并将 Pages 的部署源设为 gh-pages 分支根目录。预览横幅和 preview.json 记录实际 PR head commit。

工具 MIT；RTT 保留 [SEGGER 官方许可证](https://github.com/SEGGERMicro/RTT/blob/main/LICENSE.md)。[RTT 文档](https://kb.segger.com/RTT)。不隶属于 ST 或 SEGGER。
