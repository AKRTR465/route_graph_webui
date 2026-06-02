import { readdirSync, readFileSync, statSync } from 'node:fs'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const targetPaths = [
  'README.md',
  'package.json',
  'tsconfig.app.json',
  'tsconfig.json',
  'tsconfig.node.json',
  'vite.config.ts',
  'src',
  'tests',
]
const extensions = new Set(['.css', '.json', '.md', '.ts', '.vue'])
const issues = []

function collectFiles(path) {
  const stat = statSync(path)
  if (stat.isDirectory()) {
    for (const entry of readdirSync(path)) {
      collectFiles(join(path, entry))
    }
    return
  }
  if (extensions.has(extname(path))) {
    checkFile(path)
  }
}

function checkFile(path) {
  const text = readFileSync(path, 'utf8')
  const relative = path.slice(root.length).replaceAll('\\', '/')
  if (text.length > 0 && !text.endsWith('\n')) {
    issues.push(`${relative}: missing final newline`)
  }
  text.split(/\n/).forEach((line, index) => {
    const normalized = line.endsWith('\r') ? line.slice(0, -1) : line
    if (/[ \t]+$/.test(normalized)) {
      issues.push(`${relative}:${index + 1}: trailing whitespace`)
    }
  })
}

for (const target of targetPaths) {
  collectFiles(join(root, target))
}

if (issues.length > 0) {
  console.error(issues.join('\n'))
  process.exit(1)
}
