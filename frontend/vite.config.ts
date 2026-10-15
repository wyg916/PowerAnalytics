import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || process.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
const frontendDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(frontendDir, '..');

function git(...args: string[]) {
  try {
    return execFileSync('git', ['-C', projectRoot, ...args], { encoding: 'utf8' }).trim() || 'unknown';
  } catch {
    return 'unknown';
  }
}

function gitStatusIsDirty() {
  try {
    return execFileSync(
      'git',
      ['-C', projectRoot, 'status', '--porcelain', '--untracked-files=no'],
      { encoding: 'utf8' }
    ).trim() !== '';
  } catch {
    return true;
  }
}

const rawVersion = readFileSync(resolve(projectRoot, 'VERSION'), 'utf8').trim();
const gitSha = process.env.APP_GIT_SHA?.trim() || git('rev-parse', 'HEAD');
const gitBranch = process.env.APP_GIT_BRANCH?.trim() || git('branch', '--show-current');
const dirtyOverride = process.env.APP_WORKTREE_DIRTY?.trim().toLowerCase();
const dirty = dirtyOverride
  ? ['1', 'true', 'yes', 'on'].includes(dirtyOverride)
  : gitStatusIsDirty();
const sourceFingerprint = createHash('sha256')
  .update(resolve(projectRoot).toLowerCase(), 'utf8')
  .digest('hex')
  .slice(0, 16);
const runtimeIdentity = {
  version: rawVersion.startsWith('v') ? rawVersion : `v${rawVersion}`,
  git_sha: gitSha,
  git_branch: gitBranch,
  build_id: process.env.APP_BUILD_ID?.trim() || `${rawVersion}+${gitSha.slice(0, 12)}`,
  working_tree_dirty: dirty,
  source_fingerprint: sourceFingerprint
};

function runtimeIdentityPlugin() {
  return {
    name: 'runtime-identity',
    configureServer(server: any) {
      server.middlewares.use('/runtime-identity.json', (_request: any, response: any) => {
        response.statusCode = 200;
        response.setHeader('Content-Type', 'application/json; charset=utf-8');
        response.end(JSON.stringify(runtimeIdentity));
      });
    },
    generateBundle(this: any) {
      this.emitFile({
        type: 'asset',
        fileName: 'runtime-identity.json',
        source: JSON.stringify(runtimeIdentity, null, 2)
      });
    }
  };
}

export default defineConfig({
  plugins: [react(), runtimeIdentityPlugin()],
  define: {
    __APP_RUNTIME_IDENTITY__: JSON.stringify(runtimeIdentity)
  },
  build: {
    chunkSizeWarningLimit: 1400,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('echarts-for-react')) return 'vendor-echarts-react';
          if (id.includes('echarts')) return 'vendor-echarts';
          if (id.includes('zrender')) return 'vendor-zrender';
          if (id.includes('antd') || id.includes('@ant-design') || id.includes('/rc-') || id.includes('@rc-component')) return 'vendor-antd';
          return undefined;
        }
      }
    }
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': apiProxyTarget
    }
  }
});
