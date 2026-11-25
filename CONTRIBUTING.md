# 团队 Git 提交与协作规范

> 适用范围：废品报价项目（`feipinbaojia`）。
> 技术栈：原生 HTML + 内联 JS、Python 标准库脚本、JSON 数据文件、GitHub Actions + GitHub Pages。
> 本规范兼顾「团队通用约定」与「本项目踩过坑后固化的硬规则」，后者标为 **【项目硬规则】**，违反必出问题。

---

## 一、分支策略

项目规模小、迭代快，采用简化版 GitHub Flow，不搞 Git Flow 的多长期分支。

| 分支 | 用途 | 谁可以写 |
|---|---|---|
| `main` | 唯一长期分支，始终处于可部署状态（Pages 从它构建） | 维护者合并；Actions 机器人自动提交 |
| `feat/*` | 新功能 | 开发者 |
| `fix/*` | 修复缺陷 | 开发者 |
| `docs/*` | 文档变更 | 开发者 |
| `refactor/*` | 不改变外部行为的重构 | 开发者 |
| `chore/*` | 配置、依赖、版本号等杂项 | 开发者 |

命名规则：

- 格式 `<type>/<短描述>`，全小写、短横线分隔、不超 5 个单词。
- 禁止中文、空格、下划线开头、大写字母。
- 示例：`feat/region-price-coef`、`fix/parse-ton-price`、`chore/sw-v37`。

**【项目硬规则】** 本仓库目前通过 GitHub API 直接提交到 `main`，本地没有 git 仓库。这是一次性特例，不代表可以跳过评审。任何手动改动仍必须走「本地验证 → PR/审查 → 合并」流程；只有 `github-actions[bot]` 的 `[auto]` 提交可以直接落 `main`。

---

## 二、Commit Message 规范

采用 Conventional Commits 的简化版，中文 subject 优先（团队沟通成本低）。

### 2.1 格式

```
<type>(<scope>): <subject>

[可选正文：说明为什么，不重复改了什么]

[可选脚注：Refs #12]
```

- `type` 和 `subject` 必填，`scope` 可选。
- 一行 subject 不超过 50 个汉字，祈使语气（「修复」不是「修复了」），结尾不加句号。
- 正文每行不超过 72 字符，解释动机与取舍，不写「改了几行」。

### 2.2 type 枚举

| type | 含义 | 示例场景 |
|---|---|---|
| `feat` | 新功能 | 新增地区系数筛选 |
| `fix` | 修复缺陷 | 吨价被当成公斤价 |
| `docs` | 文档 | 新增本规范 |
| `refactor` | 重构，行为不变 | 抽公共渲染入口 |
| `perf` | 性能 | 减少重复 DOM 查询 |
| `test` | 测试 | 补解析单测 |
| `chore` | 杂项 | 升缓存版本、改 workflow |
| `auto` | 自动任务提交，bot 专用 | 定时抓价 |
| `revert` | 回滚 | 撤销某次提交 |

### 2.3 scope 参考值

`price`（报价数据/解析）、`forecast`（预测）、`outlook`（研判页）、`admin`（后台）、`sw`（Service Worker）、`workflow`（CI）、`docs`。

### 2.4 合格示例

```
fix(price): 修正后台吨价当公斤价解析导致差1000倍
feat(forecast): 接入 Mysteel 公开行情作补充源并带真实涨跌
docs: 新增团队 Git 提交规范与编码规范
chore(sw): 升缓存版本到 v37 以刷新首页样式
auto: 价格更新 2026-11-25 09:30
```

### 2.5 不合格示例与原因

```
更新了价格              # 无 type，看不出性质
fix: 修了一些 bug       # subject 太空，不知道修了什么
feat: 加了功能。        # 结尾带句号
Fix(Price): 改价格       # type/scope 大小写混用
fix(price): 改了3个文件  # 描述的是 diff 不是意图
```

---

## 三、【项目硬规则】提交前必查清单

这几条是本项目实际踩过的坑，不是形式主义。漏一条线上就会出问题。

### 3.1 改了会被 Service Worker 缓存的文件 → 升 `sw.js` 的版本号

受影响文件：`index.html`、`admin.html`、`outlook.html`、`manifest.json`、`icon.png`、`xlsx.full.min.js`、`quotes.json`、`forecast.json`、`outlook.json`。

这些文件在 SW 里走 Cache First。改了内容但没升 `CACHE_NAME`（当前形如 `scrap-price-cache-v36`），老用户拿到的还是旧页面，而且很难排查。

```
chore(sw): 升缓存版本到 v37
```

例外：`prices.json` 走 Network First，**不需要**为此升版本；但手动改它时要在提交信息里写清改动来源。

### 3.2 改了基准价 → 三处同步

同一份价格存在三个地方，必须完全一致：

1. `prices.json` → `categories[品类][品项]`
2. `index.html` → `REC_PRICES[品类][品项].price`（兜底数据）
3. `admin.html` → `getDefaultPrices()[品类][品项]`（兜底数据）

缺一处，离线或加载失败时前端显示的价就和后台对不上。曾有「审计脚本用对象减数字得 NaN，误判三源一致」的教训，比对时必须取 `.price` 字段再比，不能用减法。

### 3.3 改了价格源脚本 → 必须云端实跑一次

本地 curl 能抓到 ≠ GitHub Actions 能抓到。境外 IP 访问国内站会超时，已经出现过两次：

- `feitong` / `feilv` 子站首次云端抓取超时 → 加了 3 次重试 + 35s 超时。
- 单点源超时返回非 0 → 整条流水线后续步骤被跳过 → 改为告警不阻断。

改完 `fetch_mysteel.py` / `search_and_update.py` / `update_prices.py` 后：

```bash
python -m py_compile fetch_mysteel.py search_and_update.py update_prices.py
python fetch_mysteel.py --dry-run     # 本地先看能否解析
```

然后在 Actions 页面手动 `workflow_dispatch` 一次，检查每个步骤的结论和日志。不要只信本地结果。

### 3.4 改了数据结构 → 检查所有消费方

例如给 `prices.json` 加 `prev` 字段时，要同时确认：

- 前端 `fetchPrices` 是否读取并合并
- 两个 Python 更新脚本的 `save_prices` 是否会保留它（没变的项不能覆盖成当前价）
- 后台 `admin.html` 导出 JSON 时是否会带上它

新增字段必须在 `CONTRIBUTING.md` 或 JSON 内的说明字段里写清语义，否则下一个人会当成垃圾数据删掉。

### 3.5 前端改动的三项体检

用 Edge headless + CDP 在 390px 手机视口跑一遍：

- `document.documentElement.scrollWidth - window.innerWidth === 0`（无横向溢出）
- 页面可见文本中 0 处 `undefined` / `NaN`
- `Runtime.exceptionThrown` 为 0（语法检查查不出作用域错误，比如把注释和函数声明的换行删掉，函数会被整行注释吞掉）

### 3.6 不允许进提交的文件

`__pycache__/`、`*.pyc`、临时截图、`/tmp` 下的测试页、带 token 的任何文件。

---

## 四、Pull Request 规范

1. **一个 PR 一件事**。修 bug 和加功能分开，方便回滚。
2. **标题**沿用 commit message 格式：`fix(price): 修正吨价解析`。
3. **描述**必须包含四段：改了什么 / 为什么改 / 怎么验证 / 有什么风险。
4. **合并前**：CI 全绿、无冲突、至少一位成员看过（小改动可自审但要在描述里注明）。
5. **合并方式**：squash merge，保持 `main` 历史是一条干净的线性记录。
6. 禁止 `git push --force` 到 `main`；禁止 `--no-verify` 跳过钩子。钩子失败要先修根因。

---

## 五、环境与权限

### 5.1 本地开发（dev）

- 用 `python -m http.server` 起静态服务，不要直接 `file://` 打开（fetch 会被浏览器拦）。
- SW 会缓存旧页面，调试时用无痕窗口或 DevTools 勾选 Disable cache。
- 本地不蒜子浏览量会显示异常大的公共桶数字，那是 Referer 分桶，不是线上真实值。

### 5.2 生产环境（prod）

- 唯一入口是 `main` 分支 + GitHub Actions 自动部署。
- 所有密钥用 GitHub Secrets；本地凭据用 `git credential fill` 临时读取，**绝不写进仓库文件或提交信息**。
- 后台 `admin.html` 是纯静态页、没有鉴权，不要在里面放任何敏感信息，也不要把它当成真正的权限系统。
- 行情源只读公开页面，不碰需要登录的内容。robots.txt 明确禁止的路径不要抓。

### 5.3 自动提交的识别

bot 提交固定格式：`[auto] 价格更新 YYYY-MM-DD HH:MM`，作者为 `github-actions[bot]`。人工提交不要用 `[auto]` 前缀，方便用 `git log` 区分机器和人。

---

## 六、常见坑速查

| 现象 | 根因 | 处理 |
|---|---|---|
| 页面改了但用户看不到 | SW 缓存没升版本 | 升 `CACHE_NAME` |
| 首页和后台价格对不上 | 三源没同步 | 同步 `prices.json` / `REC_PRICES` / `getDefaultPrices` |
| 价格差 1000 倍 | 吨价当公斤价 | 后台解析已自动折算，不要绕过它 |
| 涨跌列全是 `-` | 没有历史价 | 服务端 `prev` 字段，改价时记录变动前的价 |
| 定时任务没跑 | GitHub 调度丢弃/延迟 | 多触发点 + 2 小时幂等；页面黄条兜底 |
| 云端抓不到但本地能抓 | 境外 IP 超时 | 重试 + 超时，失败降级为警告不中断 |
| 整个函数消失、页面空白 | 注释吞掉函数声明 | 改完看 `Runtime.exceptionThrown`，别只做语法检查 |
| 交叉核对显示「分歧」 | 人工判断与词频不一致 | 设计如此，只提示不改方向；样本少时忽略 |

---

## 七、提交前 60 秒自检

```bash
# 1. Python 语法
python -m py_compile *.py

# 2. 确认三源一致（示例：取 .price 字段逐个比）
node -e "const p=require('./prices.json');console.log(Object.keys(p.categories).length,'个品类')"

# 3. 确认 SW 版本是否随前端改动升级
grep CACHE_NAME sw.js

# 4. 确认没有临时文件
ls -a | grep -E 'pycache|\.pyc|tmp|test'
```

再对照第 3 节的硬规则逐条过一遍，然后提交。
