# 拾光 Frame 测试报告

项目性质：CS3331 软件工程作业。执行角色：TestEngineer；应用代码由 CodeWriter 实现，并在 CodeReviewer 最终复评通过后冻结供本轮测试。

2026 年 10 月 10 日（Asia/Shanghai）的最终本机结果：**后端 54 项，53 通过、0 失败、0 错误、1 跳过；浏览器 16 项全部通过。** 跳过项是创建真实符号链接需要当前 Windows 账户没有的权限，不能计入通过。真实 Windows 目录联接（junction）的越界及循环用例已执行通过；另有确定性替身测试覆盖扫描时跳过符号链接的分支。

## 环境与执行范围

| 项目 | 实际环境 |
| --- | --- |
| 操作系统 | Windows build 26200，Python 报告平台 `Windows-10-10.0.26200-SP0` |
| Python | Anaconda Python 3.10.20，`cheshi_handedit` 环境 |
| 本机 Python 路径 | `${PYTHON_ENV}\python.exe` |
| Node | v24.19.0，Codex bundled runtime |
| 浏览器 | Microsoft Edge 154.0.4258.48，Playwright headless 独立上下文 |
| 后端最终开始时间 | 2026-10-10 20:22:35（北京时间；JSON 记录 UTC） |
| 后端最终耗时 | 1.275454 秒（运行器整体计时） |
| 浏览器最终时间 | 2026-10-10 20:33:45.452—20:33:48.823（北京时间；JSON 记录 UTC） |
| 浏览器最终计时 | 整体时间跨度 3.371 秒；16 项断言步骤的 `seconds` 合计 2.6144 秒（其余是初始化与收尾） |
| 运行方式 | 人工临时媒体目录、`127.0.0.1` 临时端口、真实 HTTP 请求 |
| 播放素材 | 离线绘制的 JPG 与约 4 秒 H.264 MP4；没有用户私人媒体或联网下载素材 |

测试套件仅依赖 Python 标准库；应用本身也没有第三方运行依赖。浏览器验收另需 Playwright 和可用的 Edge/Chrome。测试不会调用真实系统目录选择器；目录选择成功、取消、错误、超时、忙碌及切换期间失效均使用替身验证。浏览器实际通过“输入路径”打开本地目录。

## 复现命令

在项目目录执行后端测试，并保存全部用例与错误详情：

```powershell
& "$env:USERPROFILE\miniconda3\envs\cheshi_handedit\python.exe" tests/run_tests.py
```

普通标准库测试入口也可使用：

```powershell
& "$env:USERPROFILE\miniconda3\envs\cheshi_handedit\python.exe" -m unittest discover -s tests -v
```

生成浏览器验收所需的人工图片和 H.264 视频：

```powershell
& "$env:USERPROFILE\miniconda3\envs\cheshi_handedit\python.exe" scripts/generate_demo.py --ffmpeg "D:\Tools\ffmpeg.exe"
```

在当前电脑的 bundled Playwright 环境执行浏览器验收：

```powershell
$env:NODE_PATH = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"
$env:PYTHON_EXE = "$env:USERPROFILE\miniconda3\envs\cheshi_handedit\python.exe"
$env:BROWSER_CHANNEL = "msedge"
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" tests/browser_smoke.cjs
```

其他电脑可使用自己的 Node/Playwright 安装，并将 `PYTHON_EXE`、`NODE_PATH` 指向实际位置；Chrome 可将 `BROWSER_CHANNEL` 改为 `chrome`。浏览器脚本会启动测试专用服务、复制演示素材至临时目录、保存报告和截图，最后关闭测试进程并清理人工目录。

## 后端用例分类与结果

测试实现：[tests/test_backend.py](../tests/test_backend.py)。独立运行器：[tests/run_tests.py](../tests/run_tests.py)。所有子场景由 `subTest` 执行；54 是顶层 unittest 用例数，并非把子场景重复计数后的数字。

| 测试类 | 顶层用例数 | 通过 | 跳过 | 验证内容 |
| --- | ---: | ---: | ---: | --- |
| `PathAndScanTests` | 17 | 16 | 1 | 相对路径、盘符/反斜杠/`..`/NUL 拒绝、非法根、权限错误、所有声明格式、递归图集/封面/空目录、Unicode 文件名、扫描预算、真实 Windows junction、符号链接替身 |
| `StateAndRangeTests` | 7 | 7 | 0 | 未选择目录/旧会话、根切换与凭据保持、单段/open/suffix/clamp/空文件/无效范围、未知单位及多段完整响应、拒绝非 loopback 监听 |
| `PickerUnitTests` | 3 | 3 | 0 | 选择/取消、超时/不可用、异常子进程结果；均为 subprocess 替身 |
| `HttpTests` | 27 | 27 | 0 | 真实 HTTP：启动信息、静态清单/响应头、Host/Origin/Sec-Fetch、token/非法 JSON/body、会话切换与扫描期间失效、媒体 GET/HEAD/Range、只读、选择器忙碌/失败释放/过期完成 |
| **合计** | **54** | **53** | **1** | **0 失败，0 错误** |

协议与边界测试中的具体断言包括：

- 单段 `bytes=2-5` 返回 `206`、精确字节与 `Content-Range`；open/suffix/clamp 的长度和内容正确；越界单段 `416` 包含 `bytes */20`。
- `HEAD` 即使携带有效、越界或无法解析的 `Range`，仍返回完整长度的 `200` 且没有响应体或 `Content-Range`。
- 未知范围单位和多段范围采用完整 `200` 响应；空媒体完整读取成功、单段范围请求 `416`。
- 非 ASCII token `é` 返回 `403 invalid_token`，不会触发 `500`。
- 根切换后旧图集、旧媒体返回 `409 stale_session`；扫描完成前切根也拒绝旧扫描结果。
- 选择器运行中第二次请求 `409 picker_busy`；失败或切根后旧选择结果失效，`picker_busy` 总能释放。
- 读取前后 SHA256 和修改时间完全一致，不修改媒体文件。
- 递归预算 3 时真实 `scandir` 迭代器只消费 4 项，计数最多 3；其他当前层入口仍可见。当前层独立 cap=2 时只消费 3 项、返回最多 2 项，并附 `partial` 和截断警告。消费次数由真实迭代器的轻量包装计数，未创建十万文件。

真实符号链接跳过理由：Windows `WinError 1314`（账户没有创建符号链接的特权）。真实 junction 用例使用临时目录分别构造越界目标和根目录循环，确认扫描跳过并拒绝越界媒体解析；测试后只移除联接本身。POSIX/有权限的 Windows 可执行真实符号链接用例，但本报告没有声称已在其他平台执行。

## 浏览器验收

实现：[tests/browser_smoke.cjs](../tests/browser_smoke.cjs)。16 项全部通过，均运行在独立 headless Edge 上。

| 编号 | 验收项目 | 结果 |
| --- | --- | --- |
| 1 | 欢迎页面及真实输入绝对路径打开目录 | 通过 |
| 2 | Unicode、特殊字符和 HTML 样式文件名按文本显示 | 通过 |
| 3 | 搜索、无结果提示、清除筛选 | 通过 |
| 4 | 最早修改、最近修改、名称排序 | 通过 |
| 5 | 网格/列表、浅色/深色、刷新后的偏好保持 | 通过 |
| 6 | 桌面无横向溢出、图片解码成功、图集截图 | 通过 |
| 7 | 图片前后切换、缩放/复位/双击、Esc、焦点返回原卡片 | 通过 |
| 8 | 嵌套图集及面包屑返回父级 | 通过 |
| 9 | 图片/视频筛选及图集过滤 | 通过 |
| 10 | 真实 H.264 播放时间前进、seek、关闭后释放视频 | 通过 |
| 11 | 延迟图集加载时操作搜索/排序/筛选/视图不恢复旧图集 | 通过 |
| 12 | 统计未完成的图集在图片/视频筛选中继续保留入口 | 通过 |
| 13 | 空媒体库、非法手动路径及对话框错误提示 | 通过 |
| 14 | 图集被删除后的真实 `404` 提示与面包屑恢复 | 通过 |
| 15 | 390×844 窄屏与图片查看器无横向溢出、可关闭 | 通过 |
| 16 | 没有 JavaScript 未捕获异常或非预期 console error | 通过 |

第 10 项不是仅检查 `<video>` 标签：实际 `play()` 后等待 `currentTime` 增加至少 0.3 秒，再暂停并 seek 到 2.5 秒，等待 `seeking=false`。保存的测量为 `duration=4`、`currentTime=2.5`、`readyState=4`。

第 11 项用 Playwright 延迟真实目录 API 响应，期间实际点击筛选、输入关键词、变更排序和视图，断言旧内容仍隐藏；释放响应后断言显示目标子图集。第 12 项通过替身 API 响应注入 `partial=true/count=0` 的图集，专门验证前端不会把“未知”当作“没有媒体”；后端产生 partial 的逻辑另由单元测试实际验证。

Windows 不允许 `<` 和 `>` 出现在文件名，因此本机真实文件名使用 `中文 ［img onerror=alert(1)］ & #.jpg`。本项验证特殊字符串作为文字保留、没有生成卡片内 HTML 元素，没有声称真实创建了 Windows 禁止的文件名。

浏览器记录中 2 条 `404 Failed to load resource` 是第 13 和第 14 项主动触发的预期错误；独立记录于 `expected_console_errors`。`page_errors` 与 `unexpected_console_errors` 均为空。

## 问题、修复及回归记录

| 阶段 | 发现的问题 | 判断与处理 | 回归证据 |
| --- | --- | --- | --- |
| Reviewer 初评与复评 | 共享递归预算隐藏其他同层入口、排序前无界读取、partial 图集被筛选隐藏 | CodeWriter 改为当前层独立上限与递归剩余预算、cap+1 读取后排序、partial 图集保留入口 | 后端预算/消费次数用例与浏览器 #12 通过 |
| Reviewer 初评 | 加载途中工具栏可以重渲染旧图集 | CodeWriter 在加载开始清空旧 library/visibleMedia | 浏览器 #11 延迟加载交互通过 |
| Reviewer 初评 | HEAD 对 Range 的处理与 GET 混用、未知范围单位处理不当 | CodeWriter 让 HEAD 忽略 Range，未知单位/多段采用完整响应 | 后端协议回归及真实视频播放通过 |
| Reviewer 初评 | Python 3.10 无 `Path.is_junction`，目录联接可能重复统计或循环 | CodeWriter 以 Windows reparse attribute 检测目录联接 | Python 3.10 真实 Windows junction 越界/循环测试通过 |
| Reviewer 初评 | Unicode token 与 compare_digest 导致 500 | CodeWriter 先拒绝非 ASCII token | 实际 HTTP `é` token 返回 403 |
| TestEngineer 首次沙盒运行 | 临时目录创建/清理 `WinError 5` | 执行环境权限问题；没有把它当作应用 bug，保留记录后经获准本机执行 | 正式后端 53 项及最终 54 项均无失败/错误 |
| TestEngineer 首次浏览器执行 | 延迟路由释放后立即注销，`Route is already handled` | 测试框架缺陷；等待 route.continue 完成后注销，增加异步错误保存 | 修复后的完整 16 项通过 |
| 主控交付核验 | 浏览器 JSON 每项 `seconds` 字段误记为毫秒 | TestEngineer 将 `performance.now()` 差值除以 1000；保留旧原始证据并重新执行完整验收 | 20:27:45 完整重跑 16 项通过，新报告首项 0.4506 秒，步骤总计 2.5902 秒 |
| 公开截图准备 | 截图临时样式触发 CSP，最终控制台断言失败 | 测试工具与应用 CSP 不兼容；改用截图前临时设置路径元素的 `hidden` 属性，截图后恢复；不放宽 CSP、不删除断言 | 20:33:45 完整重跑 16 项通过，0 非预期控制台错误，四张截图不含完整本机路径 |

TestEngineer 的最终正式运行未发现新的应用缺陷。修复和回归的责任分离：Reviewer/主控提出应用问题，CodeWriter 修改应用；TestEngineer 独立编写测试。测试脚本自身的问题由 TestEngineer 修复，没有通过删除业务断言来掩盖应用失败。

## 执行材料、公开脱敏与截图

公开仓库保留以下成功和失败证据。发布前，将本机用户名、项目绝对目录、解释器目录及临时目录替换为 `${USERPROFILE}`、`${PROJECT_ROOT}`、`${PYTHON_ENV}`、`${TEMP_DIR}`；JSON 仍可解析，测试结果、时间、错误类型和断言内容不改写。完整未脱敏原件单独保存在本机被 Git 忽略的 `.qa/private-evidence-originals/`，不进入公开仓库。旧耗时单位问题仍保留并明确标注，不以最后成功记录覆盖失败：

- [首次沙盒环境错误 JSON](test-results/backend-20261010T121956749875Z.json) 与 [完整日志](test-results/backend-20261010T121956749875Z.log)：53 顶层用例，3 通过、100 错误（同一用例的 setup 和 cleanup 错误分别计入）。
- [首次正式后端 JSON](test-results/backend-20261010T122008856727Z.json) 与 [完整日志](test-results/backend-20261010T122008856727Z.log)：53 项，52 通过、1 跳过。
- [首次浏览器框架错误记录](test-results/browser-20261010T122035Z-harness-failure.log)：10 项执行通过后框架回调出错；不是成功验收。首次脚本版本崩溃前没有自动写出 JSON，此日志由 TestEngineer 手动归档终端输出，并明确标注来源。
- [最终后端 JSON](test-results/backend-20261010T122235582205Z.json) 与 [完整日志](test-results/backend-20261010T122235582205Z.log)：54 项，53 通过、1 跳过。
- [前一轮浏览器 JSON](test-results/browser-2026-10-10T12-22-10-146Z.json) 与 [完整日志](test-results/browser-2026-10-10T12-22-10-146Z.log)：16 项通过，包含视频测量和预期错误。此版本每项 `records[].seconds` 实际以毫秒计算，字段标注有误，原文保留，不能直接当作秒引用。ISO 开始/结束时间及来自视频元素的 `duration`/`currentTime` 不受这个脚本单位错误影响。
- [计时修复后浏览器 JSON](test-results/browser-2026-10-10T12-27-45-115Z.json) 与 [完整日志](test-results/browser-2026-10-10T12-27-45-115Z.log)：计时单位修复后的重新执行，16 项全部通过，`records[].seconds` 已实际换算为秒。
- [截图工具 CSP 失败 JSON](test-results/browser-2026-10-10T12-32-58-032Z.json) 与 [完整日志](test-results/browser-2026-10-10T12-32-58-032Z.log)：15 项通过、1 项失败，四次临时样式注入遭 CSP 拒绝；应用逻辑没有修改。
- [最终浏览器 JSON](test-results/browser-2026-10-10T12-33-45-452Z.json) 与 [完整日志](test-results/browser-2026-10-10T12-33-45-452Z.log)：公开截图处理兼容 CSP 后完整重跑，16 项全部通过，首项 0.4507 秒，步骤合计 2.6144 秒。
- 截图：[桌面图集](screenshots/desktop-gallery.png)、[390px 窄屏](screenshots/mobile-gallery.png)、[图片查看器](screenshots/image-viewer.png)、[视频播放器](screenshots/video-player.png)。TestEngineer 已实际打开四张图片检查可读性、裁切与控件布局；截图只包含人工演示素材，临时隐藏完整本机路径，拍摄后恢复该元素。

独立语法检查 `node --check static/app.js`、`node --check tests/browser_smoke.cjs` 与 Python `py_compile` 均通过。

## 已验证源码快照

| 文件 | SHA256 |
| --- | --- |
| `app.py` | `D340BE8C348D016C7F74CF8CC5C1AD7B671A989213F84472E16482B9DAB75F71` |
| `static/app.js` | `12851E8638B585E6F395E9A484B6F24C93AEA3B9F4B9AB7F7BFBA31E882A2C88` |
| `static/style.css` | `2ABB7C42C6261AD42F44A536B51800E3E110B3BC8418D0D841E3600DF6A19F83` |
| `static/index.html` | `E1FACA0F3DC3F5AD97A36F579C7158BA7E67E09DF491ADEA84A7CC5EAF170426` |

## 持续集成与结论边界

[GitHub Actions 工作流](../.github/workflows/tests.yml) 已实际运行：[run 38052873416](https://github.com/ppknkn/cs3331-media-browser/actions/runs/38052873416)，对应发布提交 `9da90311ebb33e1464c4e8f0fd22f585a2d0ef77`。北京时间 2026-10-10 20:41:20 创建，20:41:48 完成，整体 `completed/success`。TestEngineer 独立读取四组实际 job 日志；下表数字来自日志中的 `Ran 54 tests`、`OK` 与 `skipped`，不是根据配置推算。

| 实际环境与日志 | 总用例 | 通过 | 跳过 | unittest 耗时 | 结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| [Ubuntu / Python 3.10.22](https://github.com/ppknkn/cs3331-media-browser/actions/runs/38052873416/job/114215399756) | 54 | 53 | 1 | 0.446 秒 | 成功 |
| [Ubuntu / Python 3.12.15](https://github.com/ppknkn/cs3331-media-browser/actions/runs/38052873416/job/114215399766) | 54 | 53 | 1 | 0.598 秒 | 成功 |
| [Windows / Python 3.10.11](https://github.com/ppknkn/cs3331-media-browser/actions/runs/38052873416/job/114215399786) | 54 | 54 | 0 | 1.292 秒 | 成功 |
| [Windows / Python 3.12.10](https://github.com/ppknkn/cs3331-media-browser/actions/runs/38052873416/job/114215399660) | 54 | 54 | 0 | 1.419 秒 | 成功 |

共 216 次顶层用例执行，214 通过、2 个平台性跳过、0 失败、0 错误。Ubuntu 仅跳过 Windows 专属的真实 junction 用例；四组真实符号链接越界与循环测试全部通过，两组 Windows 真实 junction 也通过。GitHub hosted Windows 具备本机没有的符号链接创建权限，补齐该场景的实际验证；本机原来的权限跳过记录不改写。四组 `node --check static/app.js` 与 `node --check tests/browser_smoke.cjs` 均通过，CI 没有运行完整浏览器验收。它使用 GitHub 提供的明确 Python 环境，不使用本机 MSYS Python。

[GitHub API 机器可读记录](test-results/github-ci-38052873416.json) 保存正式 run/job/step 状态、时间和对应提交，具体用例输出可从上表 job 日志核验。最终报告更新只涉及文档与该记录，源码和测试逻辑与通过 CI 的提交相同。

当前可执行的本机测试全部通过，真实符号链接场景另由上述远端环境验证。仍未覆盖：真人操作系统选择器、其他浏览器/操作系统完整网页体验、所有容器/编码组合、超大真实媒体库的性能压力。代码声明格式识别不代表浏览器可解码，本轮只实际播放人工 H.264 MP4。测试采用小预算验证扫描边界，不能替代十万文件级性能测量。
