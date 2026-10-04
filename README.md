# rocom-merchant-pusher

定时调用[洛克魔法书](https://rocom.shallow.ink)开放 API 获取**洛克王国：世界**的「远行商人」商店信息，按任务推送到多个渠道。带 **Web 控制台**：可视化配置推送任务、渠道实例与全局设置。

## 功能

- **多任务**：每个任务自带触发时间 + 渠道组合（例如 8 点那次只推 Bark，16 点推 Server酱 + 企业微信）。远行商人每天 8:00/12:00/16:00/20:00 刷新，默认任务对齐到每次刷新后 5 分钟。
- **多渠道多实例**：Server 酱 / Bark / PushPlus / 企业微信应用 / WxPusher，同一种渠道可建多个实例（比如两台设备的 Bark），任务里自由勾选。
- **推送策略**：每次到点都会**真实调用接口**，推送内容严格取自本次返回（默认每次都推）；任务可开启“去重”——返回内容与上次完全一致时仅跳过推送动作，不影响接口调用。
- **容错**：接口 202（数据未就绪）/网络错误自动重试；单渠道失败不影响其他渠道。
- **WebUI**：状态面板（下次执行、上次结果）、任务/渠道增删改、按实例或按草稿测试推送、手动立即执行；默认账号密码 `admin/admin`，可在登录后修改。

接口文档：<https://rocom.apifox.cn/466047235e0>（GET）/ <https://rocom.apifox.cn/466047236e0>（POST）

## 快速开始

### 1. 准备 API Key

到 [洛克魔法书官网](https://rocom.shallow.ink/developer/api-keys) 注册登录 → 开发者 → 订阅管理中订阅 **RoCom Ingame 商店信息** → API 密钥里创建 **WeGame API Key**。

### 2. 启动

```bash
docker compose up -d --build
# 打开 http://localhost:19892
```

首次启动：在「全局设置」填 API Key → 「推送渠道」新建渠道（可建多个）→ 「推送任务」配置时间与渠道组合 → 用「发送测试」验证。

也可以环境变量一把梭（见 `.env.example`）：首次启动时配了凭据的渠道会自动播种成实例和默认任务，之后仍可在 WebUI 里调整。

### 3. 登录

控制台**默认开启登录**，初始账号密码均为 **`admin` / `admin`**。登录后在「全局设置 → 修改账号密码」中修改（修改后其他已登录会话会被踢出）。`CONSOLE_USERNAME` / `CONSOLE_PASSWORD` 环境变量仅用于首次初始化时覆盖默认值。

## 运行模式

| 命令 | 说明 |
| --- | --- |
| `python -m app.main` | Web 控制台 + 后台调度（容器默认） |
| `python -m app.main --scheduler` | 只跑后台调度，不启 Web |
| `python -m app.main --once` | 所有启用任务执行一轮后退出（配合外部 cron） |
| `python -m app.main --demo` | 内置样例数据预览消息格式 |
| `python -m app.main --show-config` | 打印当前生效配置（密钥打码） |

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `ROCOM_API_KEY` | — | 官网开发者 WeGame API Key（header `X-API-Key`） |
| `ROCOM_API_BASE` | `https://wegame.shallow.ink` | 接口基地址 |
| `ROCOM_SHOP_ID` | 空（默认远行商店 3009） | 商店 ID，逗号分隔，每个商店独立去重 |
| `ROCOM_WAIT_MS` | `8000` | 同步等待毫秒数（数据未就绪时服务端等待） |
| `ROCOM_MAX_RETRIES` / `ROCOM_RETRY_DELAY` | `3` / `20` | 202/网络错误重试次数与间隔（秒） |
| `PUSH_TITLE_PREFIX` | `洛克王国远行商人` | 推送标题前缀 |
| `WEB_PORT` | `19892` | Web 控制台端口 |
| `CONSOLE_USERNAME` / `CONSOLE_PASSWORD` | `admin` / `admin` | 首次初始化的控制台账号密码（之后在 WebUI 里修改） |
| `CONFIG_PATH` / `STATE_FILE` | `/data/config.json`、`/data/state.json` | 配置与状态文件 |
| `RUN_ON_START` | `0` | 启动容器时立即执行一轮（默认关闭，可在 WebUI 设置页修改） |
| `LOG_LEVEL` | `INFO` | 日志采集级别（控制台/文件/WebUI 日志页共用，`DEBUG` 最详细） |
| `LOG_DIR` | `/logs` | 文件日志目录（与 `/data` 同级） |
| `LOG_RETENTION_DAYS` | `7` | 文件日志保留天数，到期自动清理 |
| `SERVERCHAN_SENDKEY`、`BARK_*`、`PUSHPLUS_*`、`WECOM_*`、`WXPUSHER_*` | — | 渠道种子（首次启动播种为实例） |

完整渠道字段说明见 `.env.example`；页面内每个输入框也有提示。

## 推送效果

标题：`洛克王国远行商人｜商店3009（第3/4次）`

> 查询时间 10月4日-16:25｜来源 cache
> 商店已刷新：**3/4** 次
>
> - **美妙球**｜3000洛克贝｜限购 200｜可购 10月4日-08:00 ~ 10月5日-00:00
> - **可可果球**｜50洛克贝｜限购 20｜可购 10月4日-08:00 ~ 10月5日-00:00
> - **黄石榴石**｜1000洛克贝｜限购 100｜可购 10月4日-16:00 ~ 20:00
>
> 共 3 件商品

Server 酱/PushPlus/企微/WxPusher 收 Markdown，Bark 收等价纯文本。接口返回的都是当前货架上的商品：`next_refresh_time`（档位轮换）与 `disable_time`（显式下架）是可购窗口的**结束**时刻，取较早者；接口没有开始时间字段，**开始按档位推算**——时段商品取当前档起点（如 16:00-20:00 的黄石榴石），全天供应商品取当天 8:00 开市。

## 持久化

所有配置与状态都落在容器的 **`/data` 目录**，文件日志落在 **`/logs` 目录**（与 `/data` 同级），把宿主机文件夹映射进去即可完整持久化（docker-compose 已默认映射 `./data:/data` 与 `./logs:/logs`）：

| 文件 | 内容 |
| --- | --- |
| `/data/config.json` | 全部 WebUI 配置：API Key、渠道实例（含密钥）、推送任务、控制台登录凭据 |
| `/data/state.json` | 各 任务+商店 的数据指纹（去重） |
| `/data/scheduler_state.json` | 上次执行结果与时间（重启后状态页仍可见） |
| `/data/history.json` | 调用历史：每次成功拉取的商品信息按 商店/日期/档位 保存，默认保留 30 天（`HISTORY_DAYS` 可调），WebUI「历史记录」页展示 |
| `/logs/rocom-push.log` | 文件日志（按天滚动，默认保留 7 天，`LOG_RETENTION_DAYS` 可调，到期自动清理） |

用 `docker run` 时记得手动挂载：`-v /your/path/data:/data`。控制台登录会话存于内存，重启后需重新登录（有意为之）。

## 通知模板

「全局设置 → 通知模板」可自定义推送内容，三层模板**留空即用内置默认**，改完点「👁 用示例数据预览」看效果：

| 模板 | 可用占位符 | 内置默认 |
| --- | --- | --- |
| 标题 | `{prefix}` `{shop_id}` `{refresh_count}` `{max_refresh_count}` `{date}` `{goods_count}` | `{prefix}｜商店{shop_id}（第{refresh_count}/{max_refresh_count}次）` |
| 正文（Markdown） | `{queried}` `{source}` `{date}` `{refresh_count}` `{max_refresh_count}` `{goods_count}` `{goods_list}` `{shop_id}` | 引用行（查询时间/来源）+ 刷新轮次 + `{goods_list}` + 商品总数 |
| 商品行（每件商品一行） | `{name}` `{price}` `{limit}` `{window}` `{item_num}` `{goods_id}` | `- **{name}**｜{price}｜限购 {limit}｜{window}` |

说明：正文里的 `{goods_list}` 即商品行模板逐件渲染的结果；`{limit}`/`{window}` 等为空时会自动收起悬空的 `｜` 分隔符；Bark 等纯文本渠道收到的是模板正文的去 Markdown 版本；子商品暂不支持自定义模板（沿用内置缩进格式）。

## 常见问题

- **401**：API Key 未配置/无效，或没订阅「RoCom Ingame 商店信息」。
- **频繁 202**：查询服务尚未拿到数据，程序按重试间隔自动等待，无需处理。
- **推送没发出来**：状态页看上次执行结果；任务里渠道没勾、渠道实例缺配置、或数据无变化被去重跳过（任务上显示"无变化跳过"）。
- **想每天只推变化**：默认每次刷新都推。若只想在商品有变化时收到推送，编辑任务勾选“去重”——注意这只影响“是否推送”，每次仍会正常调用接口。
- **多商店**：`ROCOM_SHOP_ID=3009,3019`，每个商店独立指纹、独立推送。

## 项目结构

```
app/
├── main.py            # 入口与运行模式
├── config.py          # 环境变量兜底配置
├── models.py          # 渠道实例 / 任务 / 全局配置模型
├── store.py           # /data/config.json 持久化（env 播种、密钥保留、损坏备份）
├── rocom.py           # 新接口客户端（X-API-Key、202 重试）
├── format.py          # 消息格式化（Markdown + 纯文本，可购区间）
├── state.py           # 任务级指纹去重
├── scheduler.py       # 多任务调度器（时间并集、按任务分发）
└── channels/
    ├── manifest.py    # 渠道字段声明（驱动 WebUI 表单与校验）
    ├── serverchan.py / bark.py / pushplus.py / wecom.py / wxpusher.py
    └── __init__.py    # 按实例分发
    （app/web/ 为 FastAPI 控制台与静态前端）
```

架构参考了 [adrian803/roco-serverchan-notifier](https://github.com/adrian803/roco-serverchan-notifier)（MIT），并将其对接到了新版 `/ingame/merchant/info` 接口与多任务模型。
