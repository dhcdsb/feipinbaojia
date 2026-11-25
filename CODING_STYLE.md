# 编码规范

> 适用项目：`feipinbaojia`。前端为原生 HTML + 内联 JS（无框架、无构建），后端为 Python 标准库脚本，数据为 JSON。
> 规范目标：让单文件代码在多人修改下仍可读、可查、不互相踩踏。
> 标注 **【必守】** 的条目来自本项目真实故障，不是风格偏好。

---

## 一、通用原则

1. **可读优先于技巧**。不写一行流、不炫技、不省略括号。
2. **显式优于隐式**。依赖、参数、返回值都要看得见，不靠「大家知道」。
3. **不写魔法数字**。数值阈值、版本、路径抽成顶部常量。
4. **一个函数只做一件事**。超过 40 行就该想拆分。
5. **注释解释「为什么」，不解释「是什么」**。代码本身应当说明是什么。
6. **先跑通再抽象**。项目小，过度设计比重复代码更贵。

---

## 二、JavaScript（内联脚本 / sw.js）

项目没有构建工具，JS 直接写在 HTML 的 `<script>` 里或 `sw.js` 中。因此**作用域污染和命名冲突风险比框架项目高**，这是本规范的重点。

### 2.1 基础格式

- 缩进 2 空格，语句结尾加分号。
- 新代码用 `const` 优先、`let` 次之；**禁止新增 `var`**。历史代码里的 `var` 不强改，但改到哪一段就顺手收窄它的作用域。
- 字符串统一单引号；拼接用模板字符串 `` `...${x}...` ``。
- 对象字面量属性名不加多余引号（除非含连字符或中文）。
- 一行不超过 100 字符，超了就换行。
- 大括号不另起一行：

```js
function regionPrice(cat, item) {
  const base = priceData[cat] ? priceData[cat][item] : null;
  if (base == null) return null;
  return round2(base * regionCoef(cat, item));
}
```

### 2.2 命名

| 场景 | 规则 | 示例 |
|---|---|---|
| 变量 / 函数 | camelCase | `regionPrice`、`refreshView` |
| 常量 | UPPER_SNAKE_CASE | `REC_PRICES`、`PRECACHE_URLS` |
| DOM 元素变量 | 加 `El` 后缀 | `statBarEl`、`resultBoxEl` |
| 布尔值 | `is` / `has` / `can` 开头 | `isFresh`、`canScroll` |
| 渲染函数 | `render` + 模块名 | `renderTable`、`renderForecast` |
| 事件处理 | `on` + 动作 | `onPriceChange`、`onRatioChange` |

**【必守】** 渲染相关函数统一从 `refreshView()` 调用，不要在各处分散重绘。历史上「5 分钟刷新只更新了表格，下拉标注价和预警条停在旧值」就是因为漏了统一入口。新增依赖价格的区块，必须挂进 `refreshView()`。

### 2.3 作用域与依赖注入

**【必守】** 不要把函数定义在使用它的作用域之外，却引用该作用域的局部变量。

真实事故：`dirOf` 写在 `render()` 外面，却用了 `render()` 的参数 `fc`。语法检查完全通过，运行时整页报「研判数据加载失败」，页面只剩 160 个字符。

正确做法：把需要的数据提到模块级变量，或在函数内定义。

```js
// 模块级：所有 render 相关函数都能读到
var FC = null;

function render(d, prices, fc) {
  FC = fc || null;   // 注入一次，后续函数从 FC 读
  ...
}

function dirOf(c, net) {
  const f = FC && FC.categories ? FC.categories[c.cat] : null;
  ...
}
```

**【必守】** 判断 JS 是否正常，不能只做语法检查。用无头浏览器监听 `Runtime.exceptionThrown`，并断言关键区块已渲染、页面无 `undefined`/`NaN`。

### 2.4 数据流

- 单一数据源：**详情/表格/推荐卡/预测卡都从 `priceData` + `forecast` 读**，不要在多个地方各存一份。
- 同一份数据存在多文件时（如价格三源），明确谁是主源：`prices.json` 是主源，HTML 里的 `REC_PRICES` 只是兜底。
- 派生值（预测价、地区价、收货区间）**实时算，不落盘**。改了基准价要能立刻反映到所有展示位。
- 函数参数超过 3 个，改用对象传参。

### 2.5 DOM 操作

- 重复查询的元素缓存到变量，不在循环里反复 `getElementById`。
- 用 `textContent` 写纯文本，用 `innerHTML` 只在确实需要标签时；插入外部数据前必须确认是本站数据，不拼接用户输入。
- 新代码用 `addEventListener` 绑定事件；历史 inline `onclick` 不强改，但**不要新增**。
- 不用 `eval`、`document.write`。
- 动态数值统一走 `px()` 之类的格式化函数，别在各处重复 `toFixed`。

### 2.6 异步与错误

```js
async function loadSomething() {
  try {
    const resp = await fetch('data.json?t=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    if (!data || !data.categories) throw new Error('empty data');
    return data;
  } catch (err) {
    console.warn('[loadSomething] 加载失败，使用本地兜底', err);
    return null;
  }
}
```

- 所有 `fetch` 必须有 `catch`，失败要有明确兜底（本地缓存 / 空结构），不能静默。
- SW 离线兜底返回的对象型 JSON 用 `{}`，数组型用 `{ categories: {} }`，与页面预期结构一致。
- `async` 函数里不写裸 `throw` 后不处理；调用方要么 `await ... catch`，要么函数内部消化。

### 2.7 Service Worker 特则

- 数据文件（`prices.json` / `quotes.json` / `forecast.json` / `outlook.json`）走 **Network First**，保证拿到新价；其余静态资源走 **Cache First**，靠版本号控制更新。
- 缓存 key 去掉查询参数，否则带时间戳的 URL 在离线时永远匹配不到。
- 改任何被缓存的静态文件，必须升 `CACHE_NAME` 版本。详见 `CONTRIBUTING.md` 第 3.1 节。

---

## 三、Python

四个脚本均为标准库实现，无第三方依赖。保持这一点，部署环境才不会因 `pip install` 失败而中断。

### 3.1 格式

- 遵循 PEP 8：4 空格缩进，每行不超过 88 字符，UTF-8 编码。
- 模块级文档字符串说明用途、数据源、用法。
- 函数写 docstring，至少说明参数和返回值。
- 新代码加类型注解；老代码逐步补，不强求一次性全改。
- 常量集中在文件顶部：`PRICES_PATH`、`UA`、`MAX_DRIFT`、`FRESH_DAYS`。

```python
def parse_today_price(html: str) -> list[dict]:
    """解析首页今日价格表。

    Returns:
        [{name, region, price, change, date}]，解析不到返回空列表。
    """
    ...
```

### 3.2 命名

- 函数 / 变量：`snake_case`（`parse_today_price`）。
- 常量：`UPPER_SNAKE_CASE`（`PRICES_PATH`）。
- 私有函数：单下划线开头（`_normalize`）。
- 类名：`PascalCase`。

### 3.3 路径与文件

- 用 `pathlib.Path`，不要字符串拼路径：

```python
SCRIPT_DIR = Path(__file__).parent
PRICES_PATH = SCRIPT_DIR / "prices.json"
```

- 读写 JSON 显式指定 `encoding='utf-8'`；读旧文件用 `utf-8-sig` 兼容 BOM。
- 写盘用 `ensure_ascii=False, indent=2`，末尾补换行，保证 diff 可读。
- 原子性：先构造完整对象再一次写盘，不要边读边改边写。

### 3.4 网络请求

**【必守】** 所有网络请求必须带 `timeout`、重试和降级，失败不能中断整个流水线。

```python
def fetch(url: str, tries: int = 3, timeout: int = 35) -> str:
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            print(f"  [RETRY {attempt}/{tries}] {url}: {e}")
            if attempt < tries:
                time.sleep(4)
    raise last_error
```

- 可选数据源失败时打印警告并返回成功，不要 `return 1` 把后续步骤全打断。
- 解析结果必须做合理性校验：数值范围、日期新鲜度、与现价偏差阈值，三道闸缺一不可。

### 3.5 日志与脚本入口

统一前缀，方便从 Actions 日志里一眼筛选：

| 前缀 | 含义 |
|---|---|
| `[OK]` | 成功完成 |
| `[MAP]` | 数据映射/写入 |
| `[SKIP]` | 主动跳过（有明确理由） |
| `[WARN]` | 异常但已降级处理 |
| `[ERR]` | 失败且无法继续 |
| `[RETRY]` | 重试中 |
| `[PREV]` | 上次价记录变更 |

脚本统一以 `if __name__ == "__main__": sys.exit(main())` 收尾，便于被其他模块导入测试。

### 3.6 异常处理

- 具体捕获，不写裸 `except:`；确实要兜底时写 `except Exception`。
- 错误信息带上上下文（哪个文件、哪个品类、原值是多少），不要只打印 `e`。
- 降级路径必须让数据落在「明确的旧状态」，不能产出半新半旧的对象。

---

## 四、HTML / CSS

### 4.1 HTML

- 声明 `<!DOCTYPE html>` 与 `lang="zh-CN"`。
- 语义化标签：区块用 `<section>` / `<article>`，标题用 `<h1>`~`<h3>`，按钮用 `<button type="button">`。
- 表单控件必须有 `<label>` 或 `aria-label`，图标按钮加 `title`。
- 折叠控件用 `aria-expanded` 同步状态，键盘可聚焦。
- 外部第三方压缩库（如 `xlsx.full.min.js`）不纳入本规范，也不要手工修改。

### 4.2 CSS

- 主题色、间距、圆角放 `:root` 变量，不写散落的魔法色值。
- class 用 kebab-case：`fc-range`、`rec-card`、`region-tab`。保持项目现有风格，不引入 BEM 双下划线。
- 移动优先：窄屏样式为默认，宽屏用 `@media (min-width: ...)` 覆盖；项目现有反向写法（`max-width`）保留，新区块统一一种。
- 触控目标 ≥ 44px。
- 优先用 CSS 变量适配深浅色主题，不硬编码背景色。
- 尽量不用行内 `style`，只有动态计算值（如进度条宽度）例外。

---

## 五、JSON 数据文件

- 2 空格缩进，UTF-8 无 BOM，末尾换行。
- **键名一旦发布就不能改**（前端多处硬编码），只能新增。
- 价格用数字类型，不用字符串；单位是「元/公斤」，在文档里约定，不塞进字段名。
- 时间用 ISO 8601 带时区：`2026-11-25T09:30:00+08:00`。
- 新增字段必须写清语义并被所有消费方确认。当前特殊字段：

| 字段 | 含义 | 注意 |
|---|---|---|
| `prev` | 上一次的报价，用于涨跌 | 价格没变时**保留旧值**，不能覆盖成当前价 |
| `prevNote` | prev 的口径说明 | 供人阅读，前端不依赖 |
| `coefs` | 地区系数 | 品类名 + 品项名做 key，7 个地区均值须为 1 |
| `fc7` / `fc30` | 7 天 / 30 天幅度 | 30 天区间必须包含 7 天区间 |

- 改结构前先列出所有消费方：前端三个页面、两个 Python 脚本、后台导出逻辑。

---

## 六、注释规范

### 6.1 必须写注释的情况

1. 违反直觉的口径（比如「涨跌按市场上一期价，不是本站调价幅度」）。
2. 踩过坑的地方（比如「对象减数字得 NaN，比较必须用 `.price` 字段」）。
3. 兼容旧数据的分支（比如「08-06 的陈旧行要过滤」）。
4. 非显然的约束（比如「30 天区间必须包含 7 天」）。

### 6.2 不要写

- 复述代码的注释：`// 设置价格`。
- 过时的注释：改完代码顺手改注释，宁可删掉也别留错的。
- 大段被注释掉的旧代码，用 Git 历史找回。

---

## 七、错误处理与数据校验

| 层级 | 要求 |
|---|---|
| 抓取 | 超时、重试、日期过滤、数值范围校验、偏差阈值 |
| 解析 | 解析不到返回空结构，不抛异常给上层；打印 `[WARN]` |
| 写盘 | 全量构造后再写，不让中间状态落盘 |
| 前端 | 空数据兜底、字段缺失兜底、禁止渲染 `undefined` / `NaN` |
| SW | 离线返回结构正确的空对象，让页面识别为「无数据」而不是「同步成功」 |

**【必守】** 禁止吞掉异常不打印。哪怕是刻意降级，也要留一行带上下文的日志。

---

## 八、质量门禁

提交前按顺序执行：

```bash
# Python 语法
python -m py_compile *.py

# JS 语法（sw.js 是独立文件）
node --check sw.js

# 抓取脚本 dry-run（改过脚本时）
python fetch_mysteel.py --dry-run

# 关键页面实机检查（390px 手机视口）
# 断言：表格行数=58、无横向溢出、无 undefined/NaN、无 JS 异常
```

前端改动还应确认 `sw.js` 缓存版本已升级，价格改动应确认三处价格源一致。详细清单见 `CONTRIBUTING.md` 第 3 节。

---

## 九、dev / prod 差异

| 维度 | dev（本地） | prod（GitHub Pages + Actions） |
|---|---|---|
| 数据来源 | 可手改 JSON 任意测试 | 只由脚本或后台导出写入 |
| 缓存 | SW 会干扰，用无痕或禁缓存 | 靠 `CACHE_NAME` 版本强制更新 |
| 抓价 | 直接 curl，超时短 | 境外 IP，必须重试 + 长超时 |
| 失败处理 | 可以直接报错停下 | 必须降级，不能阻断后续步骤 |
| 密钥 | `git credential fill` 临时读取 | 只用 GitHub Secrets |
| 日志 | 看终端 | 看 Actions 日志，靠 `[OK]/[WARN]` 前缀筛选 |
