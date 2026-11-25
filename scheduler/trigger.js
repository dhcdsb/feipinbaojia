/**
 * 废品报价 - 外部定时任务触发器（Cloudflare Worker）
 *
 * 作用：按固定时间调用 GitHub 的 workflow_dispatch 接口，触发价格抓取。
 * 为什么不用 GitHub 自带 cron：它在高峰期会延迟数小时甚至丢弃任务，
 * 已实测出现「配置 09:30 却跑到凌晨 03:00」。改由 Cloudflare 按时发球。
 *
 * 触发后 GitHub 那边仍走原有的 2 小时幂等判断，所以本脚本每天调两次即可，
 * 和 GitHub 自带的兜底 cron 撞车也不会重复抓。
 *
 * 需要的环境变量（在 Cloudflare 后台以 Secret 形式配置，不要写进代码）：
 *   GH_TOKEN  - 有 Actions:write 权限的 GitHub Token
 *   GH_REPO   - 仓库路径，格式 owner/repo，例如 dhcdsb/feipinbaojia
 *   WORKFLOW  - workflow 文件名，默认 update-prices.yml
 *   FORCE     - 可选，设为 'true' 时忽略 2 小时幂等（日常不要设）
 */

const DEFAULT_WORKFLOW = 'update-prices.yml';
const RETRY_TIMES = 2;      // 网络抖动重试次数
const RETRY_DELAY_MS = 3000;

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 组装调用地址。workflow 文件名做 URL 编码，避免特殊字符出错。
 */
function buildUrl(env) {
  const repo = env.GH_REPO || 'dhcdsb/feipinbaojia';
  const workflow = env.WORKFLOW || DEFAULT_WORKFLOW;
  return `https://api.github.com/repos/${repo}/actions/workflows/${encodeURIComponent(workflow)}/dispatches`;
}

/**
 * 真正发一次请求。GitHub 返回 204 表示已受理（没有响应体）。
 * 4xx 是配置问题（token 没权限、仓库名错），重试也没用，直接抛错停下。
 * 5xx / 网络错误可重试。
 */
async function dispatchOnce(env, force) {
  const response = await fetch(buildUrl(env), {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.GH_TOKEN}`,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'feipinbaojia-scheduler',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      ref: 'main',
      inputs: { force }
    })
  });

  if (response.status === 204) {
    return { ok: true, status: 204, retryable: false };
  }

  const detail = (await response.text().catch(() => '')).slice(0, 300);
  const retryable = response.status >= 500 || response.status === 429;
  console.error(`[ERR] HTTP ${response.status}: ${detail}`);
  return { ok: false, status: response.status, retryable };
}

/**
 * 带重试的触发入口。返回是否成功，方便调用方记录日志。
 */
async function trigger(env, source) {
  if (!env.GH_TOKEN) {
    console.error('[FATAL] 缺少 GH_TOKEN，请在 Cloudflare 后台配置 Secret');
    return false;
  }

  const force = String(env.FORCE || '').toLowerCase() === 'true';

  for (let attempt = 1; attempt <= RETRY_TIMES; attempt++) {
    try {
      const result = await dispatchOnce(env, force);
      if (result.ok) {
        console.log(`[OK] ${source} 已触发价格更新 (force=${force})`);
        return true;
      }
      if (!result.retryable) {
        console.error(`[FATAL] ${source} 配置错误 HTTP ${result.status}，停止重试`);
        return false;
      }
    } catch (e) {
      console.warn(`[WARN] ${source} 第 ${attempt} 次请求异常: ${e.message}`);
    }
    if (attempt < RETRY_TIMES) await sleep(RETRY_DELAY_MS);
  }

  console.error(`[FAIL] ${source} 触发失败，已重试 ${RETRY_TIMES} 次`);
  return false;
}

export default {
  /**
   * Cron 触发入口。waitUntil 保证请求不会因 Worker 提前结束而被掐断。
   */
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(trigger(env, `cron:${controller.cron}`));
  },

  /**
   * 手动验证入口：用浏览器访问 Worker 域名，看返回内容确认链路是否通。
   * 只有带正确 key 才能触发，避免任何人都能调你的工作流。
   * 用法：https://<你的worker>.workers.dev/?key=<ADMIN_KEY>
   */
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const key = url.searchParams.get('key');
    if (!env.ADMIN_KEY || key !== env.ADMIN_KEY) {
      return new Response('Forbidden: invalid key', { status: 403 });
    }
    const force = url.searchParams.get('force') === '1';
    const scopedEnv = force ? { ...env, FORCE: 'true' } : env;
    const ok = await trigger(scopedEnv, 'manual');
    return new Response(ok ? 'OK: dispatched\n' : 'FAIL: check worker logs\n', {
      status: ok ? 200 : 500,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' }
    });
  }
};
