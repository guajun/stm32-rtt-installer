# Windows / WSL CubeMX 工程端到端测试

测试日期：2026-11-10（Asia/Shanghai）。测试安装核心来自 PR #1 的 b6f5b6f；测试工程为用户提供的 tests/e2e-install，STM32H573 / Cortex-M33。

## 结果

**16 个平台×场景组合全部通过，共完成 32 次 Debug / Release 配置、编译及 ELF 链接。**

| 场景 | Windows：Debug / Release | WSL：Debug / Release |
| --- | --- | --- |
| 未安装 RTT 的原始基线 | 通过 / 通过 | 通过 / 通过 |
| 官方 Release pack | 通过 / 通过 | 通过 / 通过 |
| 官方 GitHub 源码 ZIP | 通过 / 通过 | 通过 / 通过 |
| 指定 HTTPS pack | 通过 / 通过 | 通过 / 通过 |
| 指定 HTTPS 源码 ZIP | 通过 / 通过 | 通过 / 通过 |
| 本地 pack（无 Git / 无可用 HTTP 代理） | 通过 / 通过 | 通过 / 通过 |
| 本地 ZIP（无 Git / 无可用 HTTP 代理） | 通过 / 通过 | 通过 / 通过 |
| Git submodule | 通过 / 通过 | 通过 / 通过 |

所有 RTT 场景均在测试副本的 CubeMX USER CODE 区域加入 SEGGER_RTT_WriteString 和 SEGGER_RTT_printf 调用；检查 ELF 中存在这两个函数及 _SEGGER_RTT 控制块，避免仅添加文件却被链接器移除。submodule 检查 gitlink；纯源码检查无 .git 元数据。每个安装场景重复执行，确认 CMake、清单和接入文件字节不变。

本地包安装仅给 Python 留出 PATH，确认找不到 Git；HTTP/HTTPS 代理设为不可达地址，安装依然通过。随后恢复正常测试环境进行 CMake 构建。

用户原工程 1,514 个文件在两个平台的测试前后 SHA256 一致。工程副本、RTT 调用和测试所需 Git 仓库均只创建在测试工作目录中。没有进行上板烧录或 J-Link 实机日志测试。

## 工具版本

| 工具 | Windows | WSL Ubuntu 26.04.1 LTS |
| --- | --- | --- |
| CMake | 4.4.4 | 4.2.3 |
| Ninja | 1.13.2 | 1.13.2 |
| Arm GCC | 14.2.1 | 14.2.1 |
| Python | 3.12.10 | 3.14.4 |
| 安装入口 | Windows PowerShell 5.1 | POSIX /bin/sh |

WSL 安装了 cmake、ninja-build、gcc-arm-none-eabi、libnewlib-arm-none-eabi、libstdc++-arm-none-eabi-newlib 及所需依赖。Python、Git 与 CA 证书也已确认可用。

WSL 自动化测试集：27 项，26 通过，1 项 PowerShell 专属入口按平台跳过。

## 重现

使用 tools/test_project.py，提供本地 CubeMX 工程、一个新的测试工作目录和报告目录。原工程会保留。此脚本不会将用户工程或构建产物加入 Git。

```sh
python tools/test_project.py --project tests/e2e-install --work-dir <新测试工作目录> --report-dir <报告目录>
```

Windows 使用 Python 调用 PowerShell 5.1；WSL 使用 python3 调用 POSIX sh。两边的依赖分别位于本机和 WSL。并行测试可用 --skip-build 复用已生成的 dist 脚本。

详细日志保存在执行测试的本地工作目录。用户提供的工程不随本报告上传。
