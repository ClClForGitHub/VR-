import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const baseUrl = process.env.CREATOR_APP_BASE_URL ?? 'http://127.0.0.1:5175';
const serverUrl = new URL(baseUrl);
const serverHost = serverUrl.hostname || '127.0.0.1';
const serverPort = serverUrl.port || '5175';
const repoRoot = path.resolve(process.cwd(), '../..');
const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, 'Z');
const outputDir = process.env.CREATOR_APP_SCREENSHOT_DIR
  ? path.resolve(process.env.CREATOR_APP_SCREENSHOT_DIR)
  : path.join(repoRoot, 'run_logs', 'frontend_checks', `creator_app_round05_${stamp}`);

const pages = ['intake', 'concept-review', 'final-review', 'delivery'];
const expectedText = {
  intake: '输入创作需求',
  'concept-review': '概念选择审稿',
  'final-review': '最终 Blender 场景验收',
  delivery: '交付完成',
};
const viewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'mobile', width: 390, height: 844 },
];

async function canReachServer() {
  try {
    const response = await fetch(baseUrl, { method: 'HEAD' });
    return response.ok;
  } catch {
    return false;
  }
}

function startDevServer() {
  return spawn(process.execPath, [
    path.join(process.cwd(), 'node_modules', 'vite', 'bin', 'vite.js'),
    '--host',
    serverHost,
    '--port',
    serverPort,
    '--strictPort',
  ], {
    cwd: process.cwd(),
    stdio: 'ignore',
  });
}

async function stopDevServer() {
  if (!serverProcess || serverProcess.killed) return;
  serverProcess.kill('SIGTERM');
  await new Promise((resolve) => {
    const timeout = setTimeout(resolve, 3000);
    serverProcess.once('exit', () => {
      clearTimeout(timeout);
      resolve();
    });
  });
}

async function waitForServer(timeoutMs = 20000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await canReachServer()) return;
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
  throw new Error(`Timed out waiting for ${baseUrl}`);
}

async function auditLayout(page) {
  return page.evaluate(() => {
    const bodyWidth = document.body.scrollWidth;
    const viewportWidth = window.innerWidth;
    const overflowSelectors = [
      'button',
      '.btn',
      '.pill',
      '.project-title',
      '.step',
      '.screen-tabs button',
      '.delivery-file-card',
      '.metadata-cards span',
      '.object-row',
      '.asset-card__meta',
      '.reference-card div',
      '.reference-tray-card',
      '.concept-option',
      '.model-viewer-status span',
    ];
    const overflowingElements = [];

    for (const selector of overflowSelectors) {
      for (const node of document.querySelectorAll(selector)) {
        const style = window.getComputedStyle(node);
        if (style.display === 'none' || style.visibility === 'hidden') continue;
        if (['auto', 'scroll'].includes(style.overflowX)) continue;
        if (node.scrollWidth > node.clientWidth + 2) {
          overflowingElements.push({
            selector,
            text: node.textContent.trim().slice(0, 80),
            clientWidth: node.clientWidth,
            scrollWidth: node.scrollWidth,
          });
        }
      }
    }

    return {
      viewportWidth,
      bodyWidth,
      horizontalOverflow: bodyWidth > viewportWidth + 2,
      overflowingElements,
    };
  });
}

let serverProcess;

try {
  await mkdir(outputDir, { recursive: true });
  if (!(await canReachServer())) {
    serverProcess = startDevServer();
    await waitForServer();
  }

  const browser = await chromium.launch();
  const results = [];

  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: 1,
    });

    for (const pageId of pages) {
      const page = await context.newPage();
      const url = `${baseUrl}/#${pageId}`;
      const errors = [];
      page.on('pageerror', (error) => errors.push(error.message));
      await page.goto(url, { waitUntil: 'networkidle' });
      await page.waitForSelector('.creator-shell', { state: 'visible', timeout: 10000 });
      const visibleText = await page.locator('.creator-shell').innerText();
      if (visibleText.trim().length < 40) {
        throw new Error(`Hydration/content check failed for ${url}`);
      }
      if (!visibleText.includes(expectedText[pageId])) {
        throw new Error(`Screen check failed for ${url}; expected text: ${expectedText[pageId]}`);
      }
      if (errors.length > 0) {
        throw new Error(`Page errors for ${url}: ${errors.join('; ')}`);
      }
      const screenshotPath = path.join(outputDir, `${viewport.name}_${pageId}.png`);
      await page.screenshot({ path: screenshotPath, fullPage: true });
      const audit = await auditLayout(page);
      results.push({ pageId, viewport, url, screenshotPath, audit });
      await page.close();
    }

    await context.close();
  }

  await browser.close();

  const failures = results.filter(
    (result) => result.audit.horizontalOverflow || result.audit.overflowingElements.length > 0,
  );
  const summary = {
    baseUrl,
    outputDir,
    checkedAt: new Date().toISOString(),
    results,
    failures,
  };

  await writeFile(path.join(outputDir, 'summary.json'), `${JSON.stringify(summary, null, 2)}\n`);

  console.log(`screenshots: ${outputDir}`);
  console.log(`checked pages: ${results.length}`);

  if (failures.length > 0) {
    console.error(JSON.stringify(failures, null, 2));
    process.exitCode = 1;
  }
} finally {
  await stopDevServer();
}
