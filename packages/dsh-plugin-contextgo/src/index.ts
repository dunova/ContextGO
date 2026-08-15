import { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import { spawn } from 'node:child_process'

export const name = 'contextgo'
export const inject = ['tools']

export interface Config {
  autoRecall?: boolean
  maxHistoryLimit?: number
}

export const Config = z.object({
  autoRecall: z.boolean().default(true).description('是否在冷启动与任务续做时自动调阅历史上下文'),
  maxHistoryLimit: z.number().default(5).description('单次召回的最大会话数 (默认: 5)'),
})

/**
 * Execute contextgo CLI command safely.
 */
function runContextGO(args: string[]): Promise<string> {
  return new Promise((resolve) => {
    try {
      const proc = spawn('contextgo', args, { stdio: ['ignore', 'pipe', 'pipe'] })
      let stdout = ''
      let stderr = ''
      proc.stdout.on('data', (d) => { stdout += d.toString('utf-8') })
      proc.stderr.on('data', (d) => { stderr += d.toString('utf-8') })
      proc.on('close', (code) => {
        if (code === 0 && stdout.trim()) {
          resolve(stdout.trim())
        } else {
          resolve(stderr.trim() || stdout.trim() || 'No matching context found.')
        }
      })
      proc.on('error', (err) => {
        resolve(`ContextGO execution error: ${err.message}`)
      })
    } catch (err: any) {
      resolve(`ContextGO process launch failed: ${err.message}`)
    }
  })
}

export function apply(ctx: Context, config: Config) {
  // 1. Register contextgo_recall
  ctx.tools?.register({
    name: 'contextgo_recall',
    description: 'Fast hybrid recall from ContextGO cross-agent memory and technical sessions. Recommended for looking up past technical solutions and architecture context.',
    parameters: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Topic, keywords, or error description' },
        limit: { type: 'number', default: config.maxHistoryLimit ?? 5, description: 'Max results' }
      },
      required: ['query']
    },
    async execute({ query, limit = 5 }) {
      const res = await runContextGO(['q', query, '--limit', String(limit)])
      return { content: [{ type: 'text', text: res }] }
    }
  })

  // 2. Register contextgo_search
  ctx.tools?.register({
    name: 'contextgo_search',
    description: 'Full-text lexical search across all indexed AI coding sessions (DeepSeek, Reasonix, Hermes, Claude Code, etc.).',
    parameters: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Literal keywords, error strings, function names' },
        limit: { type: 'number', default: 5, description: 'Max results' }
      },
      required: ['query']
    },
    async execute({ query, limit = 5 }) {
      const res = await runContextGO(['search', query, '--limit', String(limit)])
      return { content: [{ type: 'text', text: res }] }
    }
  })

  // 3. Register contextgo_semantic
  ctx.tools?.register({
    name: 'contextgo_semantic',
    description: 'Semantic search prioritizing durable architectural decisions and root causes.',
    parameters: {
      type: 'object',
      properties: {
        topic: { type: 'string', description: 'Conceptual question or architecture topic' },
        limit: { type: 'number', default: 3, description: 'Max results' }
      },
      required: ['topic']
    },
    async execute({ topic, limit = 3 }) {
      const res = await runContextGO(['semantic', topic, '--limit', String(limit)])
      return { content: [{ type: 'text', text: res }] }
    }
  })

  // 4. Register contextgo_save
  ctx.tools?.register({
    name: 'contextgo_save',
    description: 'Save a confirmed bug root cause, key architectural decision, or durable handoff note to ContextGO.',
    parameters: {
      type: 'object',
      properties: {
        title: { type: 'string', description: 'Brief title (e.g. "Decision: ...")' },
        content: { type: 'string', description: 'Detailed root cause analysis or solution' },
        tags: { type: 'string', default: '', description: 'Comma-separated tags' }
      },
      required: ['title', 'content']
    },
    async execute({ title, content, tags = '' }) {
      const args = ['save', '--title', title, '--content', content]
      if (tags) args.push('--tags', tags)
      const res = await runContextGO(args)
      return { content: [{ type: 'text', text: res }] }
    }
  })
}
