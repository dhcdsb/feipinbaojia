# 外部定时器部署指南

> 目的：解决 GitHub Actions 内置 cron 延迟/丢跑的问题。
> 原理：用外部定时器在准确时间调用 GitHub 的 `workflow_dispatch` 接口，
> GitHub 收到请求后立即启动抓取；幂等判断仍由 GitHub 那边的 workflow 做。

---

## 一、背景与现状

GitHub 的 `schedule` 事件有两个官方承认的毛病：

1. 高峰期延迟数小时——本项目实测配置为 09:30，实际跑到凌晨 03:00 前后；
2. 偶尔直接丢弃，当天一次都不执行。

仓库里已经做了两件事：

- 每个时段排 3 个 / 2 个 cron 触发点作为兜底；
- 统一 2 小时幂等——最近 2 小时内更新过就跳过所有抓取步骤。

这提高了成功率，但时间仍不受控。外部定时器负责「按时发球」，GitHub 负责「接球后干活」。

**两种触发方式的关系：**

| 触发方 | 时间 | 作用 |
|---|---|---|
| Cloudflare Worker（新增） | 北京 09:35 / 15:35 准时 | 主力，保证时效 |
| GitHub 内置 cron（保留） | 09:30/09:50/10:10、15:30/15:50 | 兜底，防 Cloudflare 侧故障 |
| 手动 / API | 随时 | 排障、强制刷新 |

因为共用 2 小时幂等，三者撞车不会重复抓、不会重复提交。

---

## 二、方案对比

| 方案 | 成本 | 可靠性 | 优点 | 缺点 |
|---|---|---|---|---|
| **Cloudflare Workers Cron**（推荐） | 免费额度足够（10 万请求/月） | 高 | 时间精确、token 存 Secret 不入库、支持重试、有手动验证入口 | 需注册 Cloudflare 账号、需一次性部署 |
| **cron-job.org** | 免费 | 中 | 纯网页配置、不写代码 | token 要交给第三方、免费版偶有延迟、任务可能被暂停 |
| GitHub 自带 cron | 免费 | 低 | 零配置 | 已证实延迟数小时/丢跑 |
| 本机 Windows 任务计划 | 免费 | 低 | 无需云服务 | 电脑关机就不跑，违背「不依赖本机」的目标 |

结论：**用 Cloudflare Workers**。项目文件已备好，你只需注册账号 + 配 4 个 Secret + 部署一次。

---

## 三、部署步骤（Cloudflare Workers）

### 3.1 准备 GitHub Token

1. 打开 <https://github.com/settings/tokens>（经典 Token）或 <https://github.com/settings/personal-access-tokens>（细粒度 Token）。
2. 生成新 Token，权限设置：
   - **经典 Token**：勾选 `repo`（或仅 `public_repo` + `workflow`）；
   - **细粒度 Token**：选择仓库 `dhcdsb/feipinbaojia`，权限给 `Actions: read and write`。
3. 复制生成的 Token（只显示一次）。

**安全提示**：不要用你本地 `git credential` 里的那个全权限 Token。单独生成一个只够触发工作流的，泄露影响最小。

### 3.2 准备 Cloudflare 账号

1. 注册 <https://dash.cloudflare.com/sign-up>（免费版即可）。
2. 进入左侧菜单 **Workers 和 Pages → Workers**。

### 3.3 方式 A：网页版直接部署（推荐，不用装工具）

1. 点 **创建 Worker**，名字填 `feipinbaojia-scheduler`，点部署。
2. 点 **编辑代码**，把本仓库 `scheduler/trigger.js` 的全部内容复制进去，部署。
3. 进入该 Worker 的 **设置 → 触发器 → Cron 触发器**，添加两个：
   - `35 1 * * 1-5`
   - `35 7 * * 1-5`
4. 进入 **设置 → 变量和机密**，添加 Secret（注意选「机密」不是「变量」）：

| 名称 | 值 |
|---|---|
| `GH_TOKEN` | 第 3.1 步生成的 Token |
| `GH_REPO` | `dhcdsb/feipinbaojia` |
| `ADMIN_KEY` | 自设一串随机口令，如 `fj2026-x7k2`（手动验证用） |

5. `WORKFLOW` 和 `FORCE` 不用设，代码里有默认值。

### 3.4 方式 B：命令行部署

本机装 Node.js 18+ 后，在项目 `scheduler/` 目录执行：

```bash
cd scheduler
npx wrangler login
npx wrangler secret put GH_TOKEN     # 粘贴 Token 后回车
npx wrangler secret put GH_REPO      # 输入 dhcdsb/feipinbaojia
npx wrangler secret put ADMIN_KEY    # 输入自设口令
npx wrangler deploy
```

`wrangler.toml` 里已经配好两个 cron，部署时会自动生效。

### 3.5 验证链路

部署完成后，浏览器访问：

```
https://feipinbaojia-scheduler.<你的账号名>.workers.dev/?key=<你设的ADMIN_KEY>
```

- 返回 `OK: dispatched` → 链路通了；
- 返回 `FAIL` → 点 Worker 的 **日志** 看具体错误（常见原因见第六节）；
- 返回 `Forbidden` → key 不对。

再去 GitHub 仓库的 **Actions** 页面，应能看到一条由 `workflow_dispatch` 触发的运行记录。

---

## 四、方案 B：cron-job.org（不想用 Cloudflare 时）

1. 注册 <https://www.cron-job.org/>。
2. 新建任务，配置：

| 字段 | 值 |
|---|---|
| URL | `https://api.github.com/repos/dhcdsb/feipinbaojia/actions/workflows/update-prices.yml/dispatches` |
| Method | `POST` |
| Schedule | `35 1 * * 1-5` 和 `35 7 * * 1-5`（两条任务） |
| Request header | `Authorization: Bearer <你的Token>` |
| Request header | `Accept: application/vnd.github+json` |
| Request header | `Content-Type: application/json` |
| Request body | `{"ref":"main","inputs":{"force":false}}` |

3. 保存后手动点「Run now」验证，去 Actions 页面看有没有新记录。

**注意**：这种方式 Token 存在第三方服务里。请务必用第 3.1 步单独生成的受限 Token，不要用全权限的。

---

## 五、日常使用与排障

### 5.1 想立刻强制更新一次

GitHub 仓库 → Actions → 选择「自动更新废品报价」→ **Run workflow** → 勾选 **force** → 运行。

勾选 force 会跳过 2 小时幂等，强制抓一次。日常定时**不要**勾。

### 5.2 检查是否按时触发

看两个地方：

- Cloudflare Worker 的 **日志**：应有 `[OK] cron:35 1 * * 1-5 已触发价格更新`；
- GitHub Actions 列表：`workflow_dispatch` 事件，时间应为北京 09:35 / 15:35 左右。

### 5.3 判断是触发器坏了还是 GitHub 坏了

| 现象 | 判断 | 处理 |
|---|---|---|
| Worker 日志有 `[OK]`，但 GitHub 没记录 | Token 权限不足或仓库名错 | 检查日志里的 HTTP 4xx，重新生成 Token |
| Worker 日志有 `[OK]`，GitHub 也有记录，但价格没变 | 幂等跳过或价格本身没动 | 看 Actions 里各步骤是否 `skipped` |
| 手动访问返回 `FAIL` | 网络或配置问题 | 看 Worker 日志的错误码 |
| 到点没触发 | Cloudflare cron 没生效 | 检查触发器的 cron 表达式是否保存 |

---

## 六、常见坑

1. **时区**：Cloudflare 和 GitHub 的 cron 都用 UTC。北京 09:35 = UTC 01:35，别填成 `35 9`。
2. **204 不是错误**：`workflow_dispatch` 成功返回 204 且无响应体，代码已按 204 判定成功，不要用 `response.ok` 之外的逻辑误判。
3. **Token 权限**：最常见的失败原因是 Token 没有 `Actions: write`。细粒度 Token 还要确认授权范围包含目标仓库。
4. **重复触发无害**：两种定时方式都过 2 小时幂等，撞车不会重复抓；但手动勾选 force 会绕过幂等，别在定时任务里用。
5. **Secret 不进仓库**：Token 只存 Cloudflare Secret 或本地环境变量，绝不要写进 `wrangler.toml` 或提交到 Git。
6. **Worker 代码更新后要重新部署**：网页版改完代码要点「部署」，命令行改完要重跑 `npx wrangler deploy`。
7. **ADMIN_KEY 别泄露**：手动验证入口靠它鉴权，泄露后任何人都能触发你的工作流（虽然幂等会挡住重复，但仍会消耗 Actions 额度）。

---

## 七、回滚

如果要停用外部定时器：

- Cloudflare：进入 Worker 的 **设置 → 触发器**，删掉两个 cron（或直接删除 Worker）；
- cron-job.org：暂停对应任务。

删除后系统退回「仅 GitHub 内置 cron」状态，即之前那种可能延迟的模式。不要删 workflow 里的 `workflow_dispatch` 配置，手动触发和排障还需要它。

---

## 八、相关文件

| 文件 | 说明 |
|---|---|
| `scheduler/trigger.js` | Worker 脚本，含重试、鉴权、手动验证入口 |
| `scheduler/wrangler.toml` | 命令行部署配置，含两个 cron 表达式 |
| `.github/workflows/update-prices.yml` | GitHub 侧工作流，含 2 小时幂等和 force 开关 |
