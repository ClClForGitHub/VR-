import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const DEFAULT_COLLECTION = 'round04d_concepts';

const CONTENT_TYPES = {
  '.json': 'application/json; charset=utf-8',
  '.jsonl': 'application/x-ndjson; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.glb': 'model/gltf-binary',
  '.gltf': 'model/gltf+json',
  '.zip': 'application/zip',
};

export function creatorBackendPlugin(options = {}) {
  const repoRoot = options.repoRoot
    ? path.resolve(options.repoRoot)
    : path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
  const runsRoot = path.join(repoRoot, 'outputs', 'runs');

  return {
    name: 'image23d-creator-backend',
    configureServer(server) {
      server.middlewares.use(async (request, response, next) => {
        const parsedUrl = new URL(request.url || '/', 'http://127.0.0.1');
        if (!parsedUrl.pathname.startsWith('/api/creator')) {
          next();
          return;
        }

        try {
          if (request.method !== 'GET') {
            sendJson(response, 405, { ok: false, error: 'creator backend currently exposes read-only GET endpoints' });
            return;
          }
          await handleCreatorApi({ request, response, parsedUrl, repoRoot, runsRoot });
        } catch (error) {
          sendJson(response, 500, { ok: false, error: error.message || String(error) });
        }
      });
    },
  };
}

async function handleCreatorApi({ response, parsedUrl, repoRoot, runsRoot }) {
  const route = parsedUrl.pathname.replace(/^\/api\/creator\/?/, '');
  const parts = route.split('/').filter(Boolean).map(decodeURIComponent);

  if (parts.length === 0) {
    sendJson(response, 200, {
      ok: true,
      api: 'image23d_creator_backend',
      default_collection: DEFAULT_COLLECTION,
      repo_root: repoRoot,
    });
    return;
  }

  if (parts[0] !== 'projects') {
    sendJson(response, 404, { ok: false, error: `unknown creator endpoint: ${parsedUrl.pathname}` });
    return;
  }

  if (parts.length === 1) {
    const collection = parsedUrl.searchParams.get('collection') || DEFAULT_COLLECTION;
    const limit = clampInt(parsedUrl.searchParams.get('limit'), 1, 500, 100);
    sendJson(response, 200, listProjects({ runsRoot, collection, limit }));
    return;
  }

  const projectKey = parts[1];
  const projectDir = resolveProjectDir(runsRoot, projectKey);
  if (parts.length === 2 || parts[2] === 'bundle') {
    sendJson(response, 200, buildProjectBundle({ runsRoot, projectDir }));
    return;
  }

  if (parts[2] === 'file') {
    sendProjectFile({ response, projectDir, relativePath: parsedUrl.searchParams.get('path') || '' });
    return;
  }

  sendJson(response, 404, { ok: false, error: `unknown project endpoint: ${parts[2]}` });
}

function listProjects({ runsRoot, collection, limit }) {
  const collectionId = canonicalCollection(collection);
  if (collectionId !== DEFAULT_COLLECTION) {
    throw new Error(`unknown creator project collection: ${collection}`);
  }

  const collectionRoot = path.join(runsRoot, 'round04d_live_12_samples');
  if (!fs.existsSync(collectionRoot)) return [];

  return fs.readdirSync(collectionRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && /^case_\d+_/.test(entry.name))
    .map((entry) => path.join(collectionRoot, entry.name))
    .filter((projectDir) => fs.existsSync(path.join(projectDir, 'state.json')))
    .sort((left, right) => path.basename(left).localeCompare(path.basename(right)))
    .slice(0, limit)
    .map((projectDir, index) => buildProjectIndexItem({ runsRoot, projectDir, collectionId, rank: index + 1 }));
}

function buildProjectIndexItem({ runsRoot, projectDir, collectionId, rank }) {
  const state = readJson(path.join(projectDir, 'state.json')) || {};
  const frontendStatus = readJson(path.join(projectDir, 'frontend_status.json')) || {};
  const artifacts = Array.isArray(state.artifacts) ? state.artifacts : [];
  const counts = artifactCounts(artifacts);
  const relativePath = relativeRunPath(runsRoot, projectDir);
  const projectKey = encodeProjectKey(relativePath);
  const stat = fs.statSync(projectDir);

  return {
    project_key: projectKey,
    run_key: projectKey,
    project_id: relativePath,
    run_id: relativePath,
    display_name: projectDisplayName({ relativePath, state }),
    relative_path: relativePath,
    run_dir: projectDir,
    effective_run_dir: projectDir,
    collection_id: collectionId,
    collection_rank: rank,
    modified_at: stat.mtimeMs / 1000,
    frontend_phase: frontendStatus.phase || state.phase || null,
    frontend_status_value: frontendStatus.status || null,
    has_state: true,
    has_summary: fs.existsSync(path.join(projectDir, 'summary.json')),
    has_frontend_status: fs.existsSync(path.join(projectDir, 'frontend_status.json')),
    has_scene_state: Boolean(findFirst(projectDir, ['scene_state.json', 'viewer_export/scene_state.json'])),
    has_viewer_scene: Boolean(findFirst(projectDir, ['viewer_scene.glb', 'viewer_export/viewer_scene.glb'])),
    concept_count: counts.concept,
    subject_concept_count: counts.subjectConcept,
    scene_concept_count: counts.sceneConcept,
    target_render_count: counts.finalPreview,
    input_image_count: counts.inputImage,
  };
}

function buildProjectBundle({ runsRoot, projectDir }) {
  const relativePath = relativeRunPath(runsRoot, projectDir);
  const projectKey = encodeProjectKey(relativePath);
  const state = readJson(path.join(projectDir, 'state.json'));
  const summary = readJson(path.join(projectDir, 'summary.json'));
  const frontendStatus = readJson(path.join(projectDir, 'frontend_status.json'));
  const sceneStatePath = findFirst(projectDir, ['scene_state.json', 'viewer_export/scene_state.json']);

  return {
    project_key: projectKey,
    run_key: projectKey,
    project_id: relativePath,
    run_id: relativePath,
    display_name: projectDisplayName({ relativePath, state: state || {} }),
    relative_path: relativePath,
    run_dir: projectDir,
    effective_run_dir: projectDir,
    state,
    summary,
    frontend_status: frontendStatus,
    scene_state: sceneStatePath ? readJson(sceneStatePath) : null,
    file_manifest: buildFileManifest({ projectDir, projectKey }),
    missing_files: ['state.json', 'summary.json', 'frontend_status.json'].filter((name) => !fs.existsSync(path.join(projectDir, name))),
  };
}

function buildFileManifest({ projectDir, projectKey }) {
  const files = [
    fileRecord({ projectDir, projectKey, label: 'state', kind: 'json', relativePath: 'state.json' }),
    fileRecord({ projectDir, projectKey, label: 'summary', kind: 'json', relativePath: 'summary.json' }),
    fileRecord({ projectDir, projectKey, label: 'frontend_status', kind: 'json', relativePath: 'frontend_status.json' }),
    fileRecord({ projectDir, projectKey, label: 'scene_state', kind: 'json', relativePath: 'viewer_export/scene_state.json' }),
    fileRecord({ projectDir, projectKey, label: 'viewer_scene', kind: 'model', relativePath: 'viewer_export/viewer_scene.glb' }),
  ];
  return {
    run_dir: projectDir,
    effective_run_dir: projectDir,
    files,
    missing_required: files.filter((file) => ['state', 'summary', 'frontend_status'].includes(file.label) && !file.exists).map((file) => file.label),
  };
}

function fileRecord({ projectDir, projectKey, label, kind, relativePath }) {
  const filePath = path.join(projectDir, relativePath);
  const exists = fs.existsSync(filePath) && fs.statSync(filePath).isFile();
  const stat = exists ? fs.statSync(filePath) : null;
  return {
    label,
    kind,
    path: filePath,
    relative_path: relativePath,
    exists,
    size_bytes: stat?.size ?? null,
    modified_at: stat ? stat.mtimeMs / 1000 : null,
    url: exists ? `/api/creator/projects/${encodeURIComponent(projectKey)}/file?path=${encodeURIComponent(relativePath)}` : null,
  };
}

function sendProjectFile({ response, projectDir, relativePath }) {
  if (!relativePath || path.isAbsolute(relativePath) || relativePath.split(/[\\/]+/).some((part) => !part || part === '.' || part === '..')) {
    sendJson(response, 400, { ok: false, error: 'invalid project file path' });
    return;
  }
  const filePath = path.resolve(projectDir, relativePath);
  if (!isInside(projectDir, filePath) || !fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    sendJson(response, 404, { ok: false, error: `missing project file: ${relativePath}` });
    return;
  }

  response.statusCode = 200;
  response.setHeader('Content-Type', CONTENT_TYPES[path.extname(filePath).toLowerCase()] || 'application/octet-stream');
  response.setHeader('Cache-Control', 'no-store');
  fs.createReadStream(filePath).pipe(response);
}

function artifactCounts(artifacts) {
  return artifacts.reduce((counts, artifact) => {
    const type = artifact.artifact_type;
    if (type === 'INPUT_IMAGE') counts.inputImage += 1;
    if (['CONCEPT_IMAGE', 'SUBJECT_CONCEPT_IMAGE', 'SCENE_CONCEPT_IMAGE', 'FINAL_PREVIEW_IMAGE', 'PREVIEW_RENDER'].includes(type)) counts.concept += 1;
    if (type === 'SUBJECT_CONCEPT_IMAGE') counts.subjectConcept += 1;
    if (type === 'SCENE_CONCEPT_IMAGE') counts.sceneConcept += 1;
    if (type === 'FINAL_PREVIEW_IMAGE' || type === 'PREVIEW_RENDER') counts.finalPreview += 1;
    return counts;
  }, { concept: 0, subjectConcept: 0, sceneConcept: 0, finalPreview: 0, inputImage: 0 });
}

function projectDisplayName({ relativePath, state }) {
  return state?.scene_spec?.title || round04dCaseLabel(relativePath) || relativePath;
}

function round04dCaseLabel(relativePath) {
  const match = String(relativePath).match(/^round04d_live_12_samples\/case_(\d+)_(.+)$/);
  if (!match) return null;
  return `Case ${match[1]} - ${titleCaseSlug(match[2])}`;
}

function titleCaseSlug(slug) {
  return slug.split('_').filter(Boolean).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
}

function canonicalCollection(collection) {
  const normalized = String(collection || DEFAULT_COLLECTION).trim().toLowerCase().replaceAll('-', '_');
  if (['round04d', 'round04d_concept', 'round04d_concepts', 'round04d_live_12_samples', 'live_12_samples'].includes(normalized)) {
    return DEFAULT_COLLECTION;
  }
  return normalized;
}

function resolveProjectDir(runsRoot, projectKey) {
  const relativePath = decodeProjectKey(projectKey);
  const projectDir = path.resolve(runsRoot, relativePath);
  if (!isInside(runsRoot, projectDir) || !fs.existsSync(projectDir)) {
    throw new Error(`creator project not found: ${projectKey}`);
  }
  return projectDir;
}

function encodeProjectKey(relativePath) {
  return `r_${Buffer.from(relativePath, 'utf8').toString('base64url')}`;
}

function decodeProjectKey(projectKey) {
  if (!projectKey.startsWith('r_')) return projectKey;
  return Buffer.from(projectKey.slice(2), 'base64url').toString('utf8');
}

function relativeRunPath(runsRoot, projectDir) {
  return path.relative(runsRoot, projectDir).split(path.sep).join('/');
}

function findFirst(root, relativePaths) {
  return relativePaths.map((item) => path.join(root, item)).find((item) => fs.existsSync(item)) || null;
}

function readJson(filePath) {
  if (!fs.existsSync(filePath)) return null;
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function sendJson(response, statusCode, payload) {
  const body = JSON.stringify(payload, null, 2);
  response.statusCode = statusCode;
  response.setHeader('Content-Type', 'application/json; charset=utf-8');
  response.setHeader('Cache-Control', 'no-store');
  response.end(body);
}

function clampInt(value, minimum, maximum, fallback) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(minimum, Math.min(maximum, parsed));
}

function isInside(root, target) {
  const relative = path.relative(path.resolve(root), path.resolve(target));
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}
