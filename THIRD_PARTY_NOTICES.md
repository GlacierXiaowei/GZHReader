# Third-Party Notices

## `rachelos/we-mp-rss`

- 上游仓库：<https://github.com/rachelos/we-mp-rss>
- 上游许可：MIT
- 固定参考提交：`c3a52fe13ff895086af53bfc5c946219549ece00`
- 提交说明：`fix: collect WeChat articles through WeRead`
- 许可证副本：`third_party/licenses/we-mp-rss-MIT.txt`

GZHReader 参考并改写了以下文件中的实现思想：

- `core/wx/model/weread_mp.py`
  - 微信读书文章列表解析
  - `originalId` 到微信文章链接的转换
  - 分页 offset 规则
  - 列表与正文请求间隔
  - 错误码分类
  - 追赶未完成时不推进游标
- `core/wx/model/test_weread_mp.py`
  - 响应解析、分页、失败恢复和正文补抓测试思路
- `core/wx/model/playwright_mp.py`
  - 浏览器请求监听与页面状态判断思路
- `driver/playwright_driver.py`
  - Playwright 生命周期和浏览器清理思路

本地实现位于：

- `src/gzhreader_core/providers/weread.py`
- `src/gzhreader_core/browser/auth.py`

本项目没有复制或运行完整的 `we-mp-rss` 仓库，也不直接 import 其 Python 包。相关逻辑已改写到 GZHReader 命名空间，并替换了数据库、配置、错误消息、任务调度和桌面通信接口。

MIT 许可证要求的版权和许可文本保存在上述许可证副本中。
