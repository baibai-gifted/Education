# Education

baibai 的教育工具与离线下载。

- **[知序 · 军事理论刷题](military-study/README.md)**：4,733 题、易混题集与自动错题本，HTML 离线使用。程序源码采用 [AGPL-3.0-only](LICENSE)。在 [Releases](https://github.com/baibai-gifted/Education/releases) 下载标题为「知序 · 军事理论刷题」的版本。
- **RecallSlide**：Windows 离线复习 PPT 工具，现有说明见下文，安装包发布状态不变。

程序许可、第三方资料和既有 RecallSlide 发布物的范围见 [NOTICE.md](NOTICE.md)。

---

# RecallSlide

面向高中英语课堂的 Windows 离线复习 PPT 工具。

导入 PDF/DOCX，选取英文单词、短语或句子，生成并编辑中文卡片，预览和导出可编辑、逐次出现的 PPTX。

## 下载

请到 [Releases](https://github.com/baibai-gifted/Education/releases) 查看经过发布验收的安装文件及版本说明。

当前公开安装文件仍在准备中。没有完整附件和安装说明的版本，请勿用于正式教学。

RecallSlide 部分仅存放必要说明，安装文件通过 Releases 分发；不包含 RecallSlide 开发源码、测试资料或用户数据。

## 安装与离线使用

每个版本的附件清单和步骤以该 Release 为准。完整离线安装资源包含模型、OCR、词库及必要运行组件，无需另装 Python、Node 或 Rust，也无需填写模型路径。

拟采用分卷下载：下载入口 EXE 及同名全部 `.7z.001` 等分卷到同一文件夹，双击入口完成解压，再进入生成目录双击安装程序。此流程尚待实际发布验收，不能只下载第一卷。

安装完成后，从桌面或开始菜单启动 RecallSlide；核心功能不依赖联网或在线 AI。

## 当前已知限制

- 选词高亮和卡片创建响应及时，但派生词及自动中文补全存在明显延迟，尚未修复。
- 部分语境的自动中文会明确报失败，需要人工核对和填写；OCR 也可能出现误识别。
- 6–8GB 实机、其他 Windows 版本、WPS 和实体翻页笔等未覆盖环境不能视为已通过。

各附件所含第三方组件及许可证以随版通知为准。发布前必须完成许可、附件完整性及实际下载安装验收。
