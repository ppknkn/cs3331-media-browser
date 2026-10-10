# CS3331 软件工程作业交付报告

项目：**拾光 Frame · 本地 Web 媒体浏览器**

日期：2026-10-10

GitHub：公开仓库 [ppknkn/cs3331-media-browser](https://github.com/ppknkn/cs3331-media-browser)

## 功能与实现

应用提供本机 Python HTTP 后端和 HTML/CSS/JavaScript 网页前端。用户选择本地根目录后，子文件夹显示为图集，支持逐层导航、图片查看器与原生视频播放器。媒体只读，默认仅监听 `127.0.0.1:8877`。应用运行使用 Python 3.10+ 标准库，不需要安装第三方运行包或前端构建工具。

界面提供手动路径与系统目录选择入口、面包屑、当前层搜索、图片/视频筛选、排序、列表/网格、浅深色外观、加载/空/错误状态。图片支持左右键切换、缩放和 Escape 关闭；视频支持原生进度、音量及全屏控件，后端单段字节范围请求支持播放器按需读取。

## 源码、测试与报告

| 交付 | 文件 |
| --- | --- |
| 后端源码 | `app.py` |
| 前端源码 | `static/index.html`、`static/style.css`、`static/app.js`、`static/favicon.svg` |
| 启动入口 | `start.bat`、`run-console.bat` |
| 演示生成源码 | `scripts/generate_demo.py` |
| 后端单元及真实 HTTP 集成测试 | `tests/test_backend.py` |
| 测试执行与证据保存 | `tests/run_tests.py` |
| 浏览器验收测试 | `tests/browser_smoke.cjs` |
| GitHub 自动验证配置 | `.github/workflows/tests.yml` |
| 完整测试报告及脱敏执行输出 | [TEST_REPORT.md](TEST_REPORT.md)、`test-results/` |
| 独立评审与复评 | [CODE_REVIEW.md](CODE_REVIEW.md) |
| 团队过程与问题记录 | [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md) |
| 可用于发表的博客稿 | [BLOG_DRAFT.md](BLOG_DRAFT.md) |
| 需求、实现说明与技术参考 | `REQUIREMENTS.md`、`IMPLEMENTATION_NOTES.md`、`TECHNICAL_REFERENCES.md` |
| 页面证据 | `screenshots/desktop-gallery.png`、`mobile-gallery.png`、`image-viewer.png`、`video-player.png` |

## 最终本机验证结果

| 验证层 | 实际结果 | 范围 |
| --- | --- | --- |
| 独立代码评审 | 4 个 P2、1 个 P3 已修复，无未解决 P0/P1 | 后端、前端、入口及文档 |
| Python / JavaScript 语法 | 通过 | CodeWriter 的编译/语法验证 |
| 后端单元与 HTTP 集成 | 54 项中 53 通过、1 跳过，0 失败、0 错误 | 指定 Windows / Python 3.10 环境 |
| 浏览器自动验收 | 16/16 通过 | 实际 Edge 浏览器、人工图片与 H.264 MP4 |
| 桌面与窄屏 | 截图复核通过 | 桌面及 390×844 CSS 像素，无横向溢出 |
| GitHub 自动验证 | 4/4 作业成功 | Ubuntu/Windows × Python 3.10/3.12；后端测试与 JavaScript 语法检查 |

后端测试覆盖格式识别、图集计数、目录边界、实际枚举工作量、会话切换、非法请求、选择器替身、文件只读、HEAD/Range 等。浏览器测试覆盖真实路径输入、导航、搜索、筛选、排序、视图与主题、图片查看器、视频时间前进及 seek 到 2.5 秒、延迟请求竞态、截断图集可达性和错误恢复。

本机 1 项跳过来自系统不允许创建真实符号链接（WinError 1314）。本机真实 Windows 目录联接越界和循环测试已通过，符号链接分支的确定性替身也通过；替身不冒充真实符号链接创建。随后远端 CI 四组真实符号链接用例均通过，两组 Windows 后端为 54/54，Ubuntu 为 53 通过、1 个 Windows 专属 junction 用例跳过。原生系统文件夹对话框的选择、取消、超时、忙碌和陈旧响应使用替身测试，真人点击系统对话框未作为实测结果。实际本地绝对路径输入与读取已通过浏览器验收。

初始受限环境执行失败、浏览器测试脚本的路由竞态、计时单位错误和公开截图工具 CSP 冲突均保留记录并说明修复；最终执行没有应用测试失败。完整运行环境、命令、各项结果和执行输出见测试报告。

## 需求验收对应

| 需求 | 状态与证据 |
| --- | --- |
| R01 前后端协作 | 通过：首页及接口真实 HTTP 验证、浏览器使用 |
| R02 本地文件夹 | 路径输入实测通过；系统选择器分支通过替身验证 |
| R03 子目录图集 | 通过：递归计数、嵌套图集与面包屑 |
| R04 图片浏览 | 通过：切换、缩放、关闭与焦点恢复 |
| R05 视频播放 | 通过：H.264 播放、时间增长、seek 与 Range/HEAD |
| R06 现代界面 | 通过：桌面/窄屏截图，工具栏与状态验收 |
| R07 只读与目录边界 | 已执行用例通过；真实符号链接权限限制单独列明 |
| R08 请求与错误边界 | 通过：Host/Origin/令牌/非法 JSON/媒体路径 |
| R09 Team 开发流程 | 已完成：开发、首轮评审、两次修补、复评、独立测试 |
| R10 完整交付文件 | 源码、测试、报告、脱敏证据已整理；原件本机保存 |
| R11 GitHub 标注作业 | 上传与远端核验记录见下方 |
| R12 博客过程总结 | 已整理：分工、真实问题、修补与经验 |

## 使用与边界

双击 `start.bat` 启动，或使用指定解释器运行 `app.py`。需要查看日志和停止服务时运行 `run-console.bat`。README 给出详细命令和演示生成方式。测试工具与应用运行依赖分开列明。

浏览器的容器和编码支持决定具体文件是否可播放；本机实测为 H.264/yuv420p MP4，不宣称所有 MOV/MP4 编码兼容。大目录采用有上限的扫描，截断时显示部分统计，进入子图集可以继续读取。网格使用原始图像 lazy loading，不生成缩略图缓存，超大照片库可能有额外解码开销。

公开仓库不包含用户媒体、演示生成的媒体文件、旧课程程序或个人课表数据库；界面截图均来自人工生成的演示素材，完整本机路径已隐藏。公开日志替换私人目录标识，未脱敏原件保留在本机被忽略的 `.qa/private-evidence-originals/`。GitHub CI 的实际执行状态与本机测试分开记录。

## GitHub 交付记录

2026-10-10 已完成公开上传，并通过 GitHub API 与远端分支核验。仓库描述明确标注 **CS3331 软件工程作业**，主题含 `software-engineering`、`cs3331`、`media-browser`、`python`、`vanilla-javascript`。

- 实现与测试提交：[9da90311ebb33e1464c4e8f0fd22f585a2d0ef77](https://github.com/ppknkn/cs3331-media-browser/commit/9da90311ebb33e1464c4e8f0fd22f585a2d0ef77)，41 个公开文件，无父提交，旧的脱敏前快照没有进入发布历史。
- 实际自动验证：[Actions run 38052873416](https://github.com/ppknkn/cs3331-media-browser/actions/runs/38052873416)，北京时间 20:41:20 创建，20:41:48 完成，整体 `success`，四组作业均 `success`。
- 可核验结果：[GitHub 机器可读 CI 记录](test-results/github-ci-38052873416.json)，含四组环境、步骤、实际时间和对应提交。
- 最终交付报告更新仅修改文档与上述 CI 记录；应用源码及测试逻辑与通过远端检查的提交一致。

首次 HTTPS 推送因现有 OAuth 登录没有 `workflow` scope 被 GitHub 拒绝；使用电脑上已经配置且验证为同一账户的 SSH 身份完成提交，无需增加权限或用户重新登录。公开材料在上传前经过路径、截图和提交身份审计，使用 GitHub noreply 邮箱。
