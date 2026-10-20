# 知序 · 军事理论刷题

黑白简约、可离线使用的互动题库，作者 **baibai**。

在 [Releases](https://github.com/baibai-gifted/military-theory-practice/releases) 下载「知序 · 军事理论刷题」ZIP，全部解压后用 Edge、Chrome 等现代浏览器打开 `index.html`。无需安装、账号或服务器。

## 功能

- 4,733 道题：单选 2,233、多选 1,300、判断 1,200；10 个辅助学习模块。
- 顺序或随机练习、题型与模块筛选、全文搜索、答案与解析。
- 1,644 道依据题面特征预标的易混题；答错自动加入个人错题本，另有收藏和续练。
- 本机保存进度，支持 JSON 备份与合并导入；明暗主题和手机布局。
- 作者页仅展示圆形头像、baibai 和发布页链接；头像已嵌入 HTML，离线可见。

原资料缺失的 101 条解析附有官方条令补充解析与引用。6 道答案冲突或题意有歧义的题保留原答案、标注待核验，不自动计分。易混标记不代表历史错误率，学习模块也不是原教材正式分类。全部原答案尚未逐题独立事实核验。

学习记录只保存在使用者自己的浏览器中，不随安装包或源码分发，不自动上传。移动 HTML、更换浏览器或清理浏览器数据可能影响记录，请定期导出备份。

## 从源码构建

需要 Python 3.10+；标准库即可，无需安装依赖。在本目录运行：

```sh
python build_app.py
python package_app.py
```

第一步生成内嵌题库和头像的 `index.html`，第二步生成 `军事理论刷题包.zip`，并检查 ZIP 与解压后文件一致。修改界面请编辑 `app-template.html`，修改头像请替换 `assets/author-avatar.jpg`。不要直接修改生成的 HTML 再运行构建。

如安装了 Node.js，可运行数据保留与脚本语法检查：

```sh
node source/check-delivery.cjs
```

浏览器验证覆盖作者页、判分、自动错题收集、续练、补充解析与待核验不计分；明暗主题和手机布局已检查。记录导入核心逻辑检查通过，实际文件选择及恢复的端到端测试尚未完成。

## 来源与许可

程序源码 Copyright © 2026 baibai，采用 **GNU AGPL-3.0-only**，许可全文见 [LICENSE](LICENSE)。程序按现状提供，不提供担保。

题库源自[公开 KDocs 资料](https://www.kdocs.cn/l/coCdkuO5iIU8)。第三方题干、选项、原解析、来源资料及头像等内容的权利归原权利人，本项目不对它们作额外授权；程序的 AGPL 许可不代替这些内容的原有权利。来源、补充解析与提取边界见 [source/README.md](source/README.md) 和 [NOTICE.md](NOTICE.md)。

项目源码与构建输入位于 military-theory-practice 仓库的 `military-study/` 目录。
