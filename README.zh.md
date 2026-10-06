# meet-telop-kit

<div align="center">

[🇺🇸 English](README.md) ｜ [🇯🇵 日本語](README.ja.md) ｜ **🇨🇳 简体中文** ｜ [🇹🇭 ไทย](README.th.md)

![左边是访谈录像，右边是加上字幕特效后的同一画面](assets/readme/hero.svg)

[![CI](https://github.com/shojikumaru/meet-telop-kit/actions/workflows/test.yml/badge.svg)](https://github.com/shojikumaru/meet-telop-kit/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![runtime](https://img.shields.io/badge/runtime-Claude%20Code%20on%20the%20web-D97757)
![platform](https://img.shields.io/badge/platform-browser-lightgrey)

把访谈录像做成约 5 分钟、YouTube 风格、带字幕特效（telop）的视频的工具包。<br>
适合因为剪辑太费时间、录像一直闲置的人。<br>
只需发送一条消息，云端的 Claude 就会剪辑、加字幕特效，并把视频送到你自己的私有副本里。

**无需安装。录像直接变成可以发布的视频。**

🔧 [工程文档](docs/engineering.md) ｜ 📘 [详细规范](.claude/skills/meet-interview-edit/SKILL.md)

</div>

[烦恼](#problems) ｜ [功能](#what-it-does) ｜ [所需条件](#requirements) ｜ [开始使用](#get-started) ｜ [为什么放心](#safety) ｜ [文档](#docs) ｜ [许可证](#license)

---

<a id="problems"></a>

## 你是否也有这些烦恼？

- **录像越积越多** — 很好的访谈一直放在 Google Drive 里没有用上
- **剪辑软件太难** — 剪切、字幕、特效都需要你没有的技能
- **字幕要花好几个小时** — 手动输入每一句字幕和人名牌就要一整天
- **外包太贵** — 每次访谈都请人剪辑，费用越来越高

---

<a id="what-it-does"></a>

## 功能

提供 Google Drive 共享链接和说话人的姓名，Claude Code on the web（在云端运行的 Claude）就会在云端电脑上完成剪辑，并把成片放进这个工具包的你自己的私有副本中。

```mermaid
flowchart LR
    A["Google Drive 链接<br/>+ 说话人的姓名"] --> B["云端的 Claude<br/>(claude.ai/code)"]
    B --> C["带字幕特效的视频<br/>（送到你的私有副本）"]
```

- 🎬 **约 5 分钟的广告版**

  Claude 从访谈中挑选有吸引力的开头和问答部分，剪成约 5 分钟。

- 💬 **YouTube 风格的字幕特效**

  说话人字幕、人名牌、问题标题、弹出数字、音效和片尾卡。

- 🖼️ **导出前先确认**

  Claude 会先给你看静态画面，你可以用普通的话提出修改。

- 📦 **送到你的私有副本**

  完成的 mp4 会出现在你自己的 GitHub 仓库里，可以直接下载。

字幕特效、分步指南和 Claude 的回复都是日语。

---

<a id="requirements"></a>

## 所需条件

所有操作都在浏览器的 claude.ai/code 中进行，与你电脑的性能无关。

- **Claude 账号** — Pro、Max、Team 或 Enterprise 方案之一
- **GitHub 账号** — 免费；视频会送到你在那里创建的私有仓库
- **放在 Google Drive 上的录像** — 以及录像中所有人的同意

| 项目 | 状态 | 说明 |
| :- | :- | :- |
| 电脑浏览器中的 Claude Code on the web | ✅ | |
| Claude Desktop 应用（Cloud） | ⚠️ | 未测试 |
| iPhone 上的 Claude 应用（Code 标签页） | ⚠️ | 本套件未在 iPhone 上测试；本指南是为电脑浏览器编写并在电脑浏览器中验证的，请在电脑上完成设置 |
| 云端电脑：Ubuntu 24.04 | ✅ | Claude Code on the web 提供的环境 |
| 在 macOS 上运行测试（`make test`） | ✅ | |
| Claude 方案 | 必需 | Pro / Max / Team / Enterprise（依据 Anthropic 的说明，2026-10-05） |
| 下载录像：Google Drive 共享链接（Meet 录像），macOS | ✅ | 用 `scripts/fetch_drive.sh` 实测（2026-10-05） |
| 下载录像：Google Drive 共享链接，云端电脑 | ⚠️ | 動作テスト只检查能否连到 Drive 的服务器；你自己的共享链接会在正式任务开始时检查 |
| 录像来源：放在 Google Drive 上的 Zoom 录像 | ⚠️ | 未测试 |

Team / Enterprise：需要管理员（Owner）允许 Claude Code on the web 和 GitHub 连接。

---

<a id="get-started"></a>

## 开始使用

只需在第一次做 3 步，每一步都有一键打开的链接。

| | 要做的事 | 打开 |
| :- | :- | :- |
| ① | **创建你自己的副本**（可见性必须选 **Private**） | <https://github.com/shojikumaru/meet-telop-kit/generate> |
| ② | **连接 Claude，并创建环境 `video`** | <https://claude.ai/code> |
| ③ | **发送「動作テスト」**（设置检查） | <https://claude.ai/code?prompt=%E5%8B%95%E4%BD%9C%E3%83%86%E3%82%B9%E3%83%88&environment=video> |

- **所需时间（估计）** — 用电脑 20–30 分钟，新注册账号再加 10–15 分钟
- **動作テスト** — 约 3–6 分钟（估计）；它会检查云端电脑能否连到 Google Drive 和 Hugging Face（语音识别模型）的服务器，10 秒的测试视频送到你的副本，就说明准备好了

用录像制作视频：在 Google Drive 中把录像共享为“知道链接的任何人”，在 claude.ai/code 中选择你的副本和 `video` 环境，填好说话人的姓名后发送指南里的请求文字。Claude 会检查链接，用静态画面征求你的确认，然后送出视频（每个视频约 30 分钟到 1 小时，估计）。

完整指南（包括点哪里、可复制的文字）见 [docs/はじめに.md](docs/はじめに.md)（日语）。

<details>
<summary>遇到问题时</summary>

- **「ネットワークにつながりません」（无法连接网络）** — 会话没有使用 `video` 环境，或允许的域名不对
- **「共有されていません」（未共享）** — 把录像的 Drive 共享设为“知道链接的任何人”
- **只返回了计划** — 把模式从“Plan”改为“Auto”或“Accept edits”后重新发送
- **列表里找不到你的副本** — 在你的副本上安装 Claude 的 GitHub App

完整列表见 [docs/はじめに.md](docs/はじめに.md) 第 7 节。

</details>

---

<a id="safety"></a>

## 为什么可以放心使用

这个工具包的设计让录像和姓名只留在你放置的地方。

- **你的副本是私有的** — 视频只会送到你自己的私有副本，不会送到别处
- **绝不编造姓名** — 缺少姓名或头衔时，Claude 会问你
- **Drive 链接只在制作时共享** — 视频送到后，把共享改回“受限”
- **网络受限** — 云端电脑只能访问列出的 6 个域名和软件包源
- **征得同意是你的责任** — 制作视频前，请先征得录像中所有人的同意

---

<a id="docs"></a>

## 了解更多

| 文档 | 读者 | 内容 |
| :- | :- | :- |
| [docs/はじめに.md](docs/はじめに.md) | 所有人（日语） | 设置、動作テスト、制作视频、故障排除 |
| [docs/engineering.md](docs/engineering.md) | 工程师（英语） | 流程、模块、交付、测试、设置 |
| [docs/engineering.ja.md](docs/engineering.ja.md) | 工程师（日语） | 同上的日语版 |
| [.claude/skills/meet-interview-edit/SKILL.md](.claude/skills/meet-interview-edit/SKILL.md) | 工程师 | Claude 遵循的操作步骤（详细规范） |
| [templates/edl_template.py](templates/edl_template.py) | 工程师 | 视频方案模板：剪辑点和字幕特效 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 贡献者 | Issue、测试、绝不能发布的内容 |
| [SECURITY.md](SECURITY.md) | 所有人 | 如何报告安全问题 |

---

<a id="license"></a>

## 许可证

[MIT](LICENSE)。希望任何人都能免费使用，并按自己的工作改造它，所以选择了 MIT。

---

<div align="center">

**无需安装** ｜ **在 claude.ai/code 中运行** ｜ **送到你的私有副本**

</div>
