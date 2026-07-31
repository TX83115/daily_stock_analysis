# 桌面端改动验证（从 AGENTS.md §6 迁出）

- 适用范围也包含仓库内的 `scripts/run-desktop.ps1`、`scripts/build-desktop*.ps1`、`scripts/build-*.sh`、`docs/desktop-package.md`。
- 默认执行：先构建 Web，再构建桌面端。
- 如受平台限制未能完整验证，需要明确说明是否验证了 Web 构建产物、Electron 构建以及 Release 工作流影响。

其余协作规则（commit 规范、PR 流程、验证矩阵总表等）以仓库根目录 `AGENTS.md` 为准。
