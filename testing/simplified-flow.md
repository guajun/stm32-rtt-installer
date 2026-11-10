# 精简流程与 release/main 复测

2026-11-10。Windows PowerShell 5.1 与 WSL Ubuntu 26.04：12 个场景 × Debug/Release × 2 个平台，共 **48 次构建通过**。测试原工程 tests/e2e-install 的 1,514 个文件保持不变，工程未上传。

| 场景 | Windows Debug / Release | WSL Debug / Release |
| --- | --- | --- |
| baseline | 通过 / 通过 | 通过 / 通过 |
| official pack | 通过 / 通过 | 通过 / 通过 |
| official github zip | 通过 / 通过 | 通过 / 通过 |
| https pack | 通过 / 通过 | 通过 / 通过 |
| https github zip | 通过 / 通过 | 通过 / 通过 |
| local pack no git | 通过 / 通过 | 通过 / 通过 |
| local github zip no git | 通过 / 通过 | 通过 / 通过 |
| submodule | 通过 / 通过 | 通过 / 通过 |
| release copy | 通过 / 通过 | 通过 / 通过 |
| main copy | 通过 / 通过 | 通过 / 通过 |
| release submodule | 通过 / 通过 | 通过 / 通过 |
| main submodule | 通过 / 通过 | 通过 / 通过 |

正式发布版 release 解析为 V8.58.0，commit `4d8feab3150f86f37a9d323ddc88d6cdf5673072`；main 快照解析为 `9106eaa39babe53e00994d7828c1afb29390cdc1`。复制与 submodule 两种方式均按该 commit 固定，重复执行不自动升级。

全部 RTT 场景加入实际输出调用，检查 ELF 中的 SEGGER_RTT_WriteString、SEGGER_RTT_printf 与 _SEGGER_RTT。每个安装重复执行检查幂等；本地包场景隔离 Git PATH 并使用不可达 HTTP 代理。submodule 仅在副本初始化 Git，并将该副本原来的“忽略全部”规则改为忽略 build/。

安装测试 29 项通过，页面检查 8 项通过。原 pack/ZIP、URL、本地包和旧 latest 语义继续覆盖。主页面只生成命令，不再在浏览器查询 GitHub 版本列表。
