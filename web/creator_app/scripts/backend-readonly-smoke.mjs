import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const repoRoot = path.resolve(process.cwd(), '../..');
const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, 'Z');
const backendUrl = (process.env.CREATOR_APP_RUNTIME_API_BASE_URL || 'http://127.0.0.1:18093').replace(/\/$/, '');
const creatorUrl = (process.env.CREATOR_APP_BASE_URL || 'http://127.0.0.1:5176').replace(/\/$/, '');
const runCollection = process.env.CREATOR_APP_RUN_COLLECTION || 'round04d_concepts';
const outputDir = process.env.CREATOR_APP_BACKEND_SMOKE_DIR
  ? path.resolve(process.env.CREATOR_APP_BACKEND_SMOKE_DIR)
  : path.join(repoRoot, 'run_logs', 'frontend_checks', `creator_app_backend_readonly_${stamp}`);

async function canReach(url) {
  try {
    const response = await fetch(url, { method: 'GET' });
    return response.ok;
  } catch {
    return false;
  }
}

function startRuntimeConsole() {
  const url = new URL(backendUrl);
  return spawn(process.env.PYTHON || 'python', [
    path.join(repoRoot, 'tools', 'runtime_console_server.py'),
    '--host',
    url.hostname || '127.0.0.1',
    '--port',
    url.port || '18093',
    '--root',
    repoRoot,
  ], {
    cwd: repoRoot,
    stdio: 'ignore',
  });
}

function startCreatorApp() {
  const url = new URL(creatorUrl);
  return spawn(process.execPath, [
    path.join(process.cwd(), 'node_modules', 'vite', 'bin', 'vite.js'),
    '--host',
    url.hostname || '127.0.0.1',
    '--port',
    url.port || '5176',
    '--strictPort',
  ], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      VITE_RUNTIME_API_BASE_URL: backendUrl,
    },
    stdio: 'ignore',
  });
}

async function waitFor(url, timeoutMs = 20000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await canReach(url)) return;
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function stopProcess(child) {
  if (!child || child.killed) return;
  child.kill('SIGTERM');
  await new Promise((resolve) => {
    const timeout = setTimeout(resolve, 3000);
    child.once('exit', () => {
      clearTimeout(timeout);
      resolve();
    });
  });
}

function apiRunsUrl() {
  const url = new URL(`${backendUrl}/api/runs`);
  if (runCollection) url.searchParams.set('collection', runCollection);
  return url.toString();
}

let backendProcess;
let creatorProcess;

try {
  await mkdir(outputDir, { recursive: true });

  if (!(await canReach(apiRunsUrl()))) {
    backendProcess = startRuntimeConsole();
    await waitFor(apiRunsUrl());
  }

  const runsResponse = await fetch(apiRunsUrl());
  const runs = await runsResponse.json();
  if (!Array.isArray(runs) || runs.length === 0) {
    throw new Error('Runtime backend returned no runs');
  }
  if (runCollection === 'round04d_concepts' && runs.length !== 12) {
    throw new Error(`Expected 12 round04d concept runs, got ${runs.length}`);
  }
  const selectedRun = runs.find((run) => run.relative_path?.includes('case_02_wuthering_beach')) || runs[0];
  const bundleResponse = await fetch(`${backendUrl}/api/runs/${encodeURIComponent(selectedRun.run_key)}/bundle`);
  const bundle = await bundleResponse.json();
  if (!bundle.frontend_status && !bundle.state) {
    throw new Error(`Selected run has no state/frontend_status: ${selectedRun.display_name}`);
  }

  if (!(await canReach(creatorUrl))) {
    creatorProcess = startCreatorApp();
    await waitFor(creatorUrl);
  }

  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const appUrl = `${creatorUrl}/?api_base=${encodeURIComponent(backendUrl)}&run_collection=${encodeURIComponent(runCollection)}&run_key=${encodeURIComponent(selectedRun.run_key)}#concept-review`;
  await page.goto(appUrl, { waitUntil: 'networkidle' });
  await page.waitForSelector('.creator-shell[data-runtime-source="backend"]', { state: 'visible', timeout: 15000 });
  await page.waitForSelector('.concept-option', { state: 'visible', timeout: 15000 });

  const domAudit = await page.evaluate(() => {
    const shell = document.querySelector('.creator-shell');
    const conceptOptions = [...document.querySelectorAll('.concept-option')];
    const conceptImages = conceptOptions.map((option) => option.querySelector('img')?.getAttribute('src')).filter(Boolean);
    return {
      source: shell?.getAttribute('data-runtime-source'),
      runKey: shell?.getAttribute('data-run-key'),
      title: document.querySelector('.project-title')?.textContent?.trim(),
      conceptOptionCount: conceptOptions.length,
      hasRuntimeConceptImage: conceptImages.some((src) => src.includes('/api/runs/') && src.includes('/file?path=')),
      runOptionCount: document.querySelectorAll('.run-select-label option').length,
      bodyWidth: document.body.scrollWidth,
      viewportWidth: window.innerWidth,
    };
  });
  const screenshotPath = path.join(outputDir, 'backend_delivery_desktop.png');
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await browser.close();

  if (domAudit.source !== 'backend') {
    throw new Error(`Creator App did not use backend source: ${JSON.stringify(domAudit)}`);
  }
  if (domAudit.runKey !== selectedRun.run_key) {
    throw new Error(`Creator App selected unexpected run: ${JSON.stringify(domAudit)}`);
  }
  if (domAudit.runOptionCount < runs.length) {
    throw new Error(`Creator App did not expose the backend run collection: ${JSON.stringify(domAudit)}`);
  }
  if (domAudit.conceptOptionCount < 1 || !domAudit.hasRuntimeConceptImage) {
    throw new Error(`Creator App did not render backend concept images: ${JSON.stringify(domAudit)}`);
  }
  if (domAudit.bodyWidth > domAudit.viewportWidth + 2) {
    throw new Error(`Creator App backend view overflowed horizontally: ${JSON.stringify(domAudit)}`);
  }

  const summary = {
    backendUrl,
    creatorUrl,
    runCollection,
    outputDir,
    selectedRun: {
      runKey: selectedRun.run_key,
      displayName: selectedRun.display_name,
      phase: selectedRun.frontend_phase,
      status: selectedRun.frontend_status_value,
    },
    bundle: {
      phase: bundle.frontend_status?.phase || bundle.state?.phase || null,
      hasFrontendStatus: Boolean(bundle.frontend_status),
      hasState: Boolean(bundle.state),
      fileCount: bundle.file_manifest?.files?.length || 0,
      artifactCount: bundle.state?.artifacts?.length || 0,
    },
    domAudit,
    screenshotPath,
    checkedAt: new Date().toISOString(),
  };
  await writeFile(path.join(outputDir, 'summary.json'), `${JSON.stringify(summary, null, 2)}\n`);

  console.log(`backend: ${backendUrl}`);
  console.log(`creator: ${creatorUrl}`);
  console.log(`run: ${selectedRun.display_name}`);
  console.log(`evidence: ${outputDir}`);
} finally {
  await stopProcess(creatorProcess);
  await stopProcess(backendProcess);
}
