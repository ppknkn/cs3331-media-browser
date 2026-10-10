# 技术依据

以下是开发与博客解释使用的官方文档，不作为本项目已实现某项能力的证明。实现证据见源码、评审及测试报告。网页读取日期：2026-10-10。

- [MDN：HTTP Range requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests)：视频播放器可以请求部分字节；有效范围通常响应 206，越界范围响应 416。验收同时检查响应头、响应体和拖动进度行为。
- [MDN：showDirectoryPicker](https://developer.mozilla.org/en-US/docs/Web/API/Window/showDirectoryPicker)：浏览器文件夹选择 API 有浏览器兼容性、用户手势和安全上下文约束。本项目由本机后端打开原生选择器，同时提供路径输入；不把浏览器目录句柄当作后端路径。
- [Python 3.10：http.server](https://docs.python.org/3.10/library/http.server.html)：标准库提供请求处理和线程式服务器的基础设施。本项目在此之上实现专用接口，并限定本机用途。
- [MDN：Web video codec guide](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Formats/Video_codecs)：视频容器和编解码器是两个维度；识别 MP4/MOV 等扩展名不等于浏览器能解码所有内容。文档与测试明确记录验证的实际编码及浏览器。
