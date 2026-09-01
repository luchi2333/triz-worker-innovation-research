#!/usr/bin/env node
/** Deterministic lookup for the bundled classical 39x39 TRIZ matrix.
 *
 * 与 lookup_matrix.py 的同名子命令输出保持一致（--self-test/--version/--search/--explain/--batch/--improve --worsen/--list-parameters）。
 * 行分片生成与校验（--emit-rows/--verify-rows）仅由 Python 版提供。
 */

import {createHash} from 'node:crypto';
import {existsSync, readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const DEFAULT_DATA = resolve(ROOT, 'references', 'contradiction-matrix.json');
const DEFAULT_GUIDANCE = resolve(ROOT, 'references', 'parameter-guidance.json');

const USAGE = [
  'Usage: node lookup_matrix.mjs --improve N --worsen N [--format markdown|json]',
  '       node lookup_matrix.mjs --batch "1x28,39x30"',
  '       node lookup_matrix.mjs --search "现场说法"',
  '       node lookup_matrix.mjs --explain 30',
  '       node lookup_matrix.mjs --list-parameters',
  '       node lookup_matrix.mjs --version',
  '       node lookup_matrix.mjs --self-test',
].join('\n');

function usageError(problem, given, fix) {
  return new Error(`${problem} | 给定: ${given} | 修复建议: ${fix}`);
}

function stableMatrixPayload(matrix) {
  return JSON.stringify(matrix);
}

function validateResource(data) {
  const {parameters, principles, matrix} = data;
  if (!Array.isArray(parameters) || parameters.length !== 39) {
    throw new Error('Expected exactly 39 engineering parameters');
  }
  if (!Array.isArray(principles) || principles.length !== 40) {
    throw new Error('Expected exactly 40 inventive principles');
  }
  if (!Array.isArray(matrix) || matrix.length !== 39 || matrix.some((row) => !Array.isArray(row) || row.length !== 39)) {
    throw new Error('Expected a 39 x 39 matrix');
  }
  if (parameters.some((item, index) => item.id !== index + 1)) {
    throw new Error('Parameter IDs must be consecutive from 1 through 39');
  }
  if (principles.some((item, index) => item.id !== index + 1)) {
    throw new Error('Principle IDs must be consecutive from 1 through 40');
  }

  let populated = 0;
  matrix.forEach((row, rowIndex) => {
    row.forEach((cell, colIndex) => {
      if (rowIndex === colIndex) {
        if (cell !== null) throw new Error(`Diagonal R${rowIndex + 1}C${colIndex + 1} must be null`);
        return;
      }
      if (!Array.isArray(cell)) throw new Error(`Off-diagonal R${rowIndex + 1}C${colIndex + 1} must be an array`);
      if (cell.some((id) => !Number.isInteger(id) || id < 1 || id > 40)) {
        throw new Error(`Invalid principle ID at R${rowIndex + 1}C${colIndex + 1}`);
      }
      if (new Set(cell).size !== cell.length) {
        throw new Error(`Repeated principle ID at R${rowIndex + 1}C${colIndex + 1}`);
      }
      if (cell.length) populated += 1;
    });
  });

  if (populated !== data.audit?.populated_cells) {
    throw new Error(`Populated-cell count mismatch: ${populated} != ${data.audit?.populated_cells}`);
  }
  const hash = createHash('sha256').update(stableMatrixPayload(matrix), 'utf8').digest('hex');
  if (hash !== data.audit?.matrix_payload_sha256) {
    throw new Error(`Matrix hash mismatch: ${hash} != ${data.audit?.matrix_payload_sha256}`);
  }
}

function loadResource(path) {
  const data = JSON.parse(readFileSync(path, 'utf8'));
  validateResource(data);
  return data;
}

function loadGuidance(path) {
  const guidance = JSON.parse(readFileSync(path, 'utf8'));
  const entries = guidance.parameters;
  if (!Array.isArray(entries) || entries.length !== 39) {
    throw new Error('parameter-guidance.json must contain exactly 39 entries');
  }
  if (entries.some((item, index) => item.id !== index + 1)) {
    throw new Error('Guidance entry IDs must be consecutive from 1 through 39');
  }
  for (const item of entries) {
    if (!Array.isArray(item.field_terms) || item.field_terms.length === 0) {
      throw new Error(`Guidance entry #${item.id} lacks field_terms`);
    }
  }
  return guidance;
}

function readSkillVersion() {
  const text = readFileSync(resolve(ROOT, 'SKILL.md'), 'utf8');
  const match = text.match(/version:\s*"([^"]+)"/);
  if (!match) throw new Error('SKILL.md frontmatter version not found');
  return match[1];
}

function lookup(data, improve, worsen) {
  if (!Number.isInteger(improve) || improve < 1 || improve > 39 || !Number.isInteger(worsen) || worsen < 1 || worsen > 39) {
    throw usageError(
      '参数编号超出范围',
      `--improve ${improve} --worsen ${worsen}`,
      '使用 1..39 的整数；运行 --list-parameters 查看参数表',
    );
  }
  const improvingParameter = data.parameters[improve - 1];
  const worseningParameter = data.parameters[worsen - 1];
  const cell = data.matrix[improve - 1][worsen - 1];
  let status;
  let guidance;
  let principleItems;
  if (cell === null) {
    status = 'physical_contradiction';
    guidance = '同一参数的相反要求不查矩阵对角线；转用时间、空间、条件或系统层级分离。';
    principleItems = [];
  } else if (cell.length === 0) {
    status = 'no_preferred_principle';
    guidance = '经典矩阵该单元没有优选原理；不得编造。复核参数映射，或转用全部 40 原理、物理矛盾、物—场分析。';
    principleItems = [];
  } else {
    status = 'ok';
    guidance = '按单元原顺序用于构思；矩阵不证明方案可行，仍须现场化解释、查新和验证。';
    principleItems = cell.map((id) => data.principles[id - 1]);
  }
  return {
    status,
    improving_parameter: improvingParameter,
    worsening_parameter: worseningParameter,
    direction: `R${improve} x C${worsen}`,
    principles: principleItems,
    guidance_zh: guidance,
    matrix_version: data.matrix_version,
  };
}

function renderMarkdown(result) {
  const improve = result.improving_parameter;
  const worsen = result.worsening_parameter;
  const principleText = result.principles.length
    ? result.principles.map((item) => `#${item.id} ${item.zh} (${item.en})`).join('；')
    : '无';
  return [
    `- 欲改善参数：#${improve.id} ${improve.zh} (${improve.en})`,
    `- 随之恶化参数：#${worsen.id} ${worsen.zh} (${worsen.en})`,
    `- 查表方向：${result.direction}`,
    `- 状态：${result.status}`,
    `- 推荐发明原理：${principleText}`,
    `- 使用提示：${result.guidance_zh}`,
  ].join('\n');
}

function renderParameters(data) {
  return [
    '| 编号 | 中文参数 | English parameter |',
    '|---:|---|---|',
    ...data.parameters.map((item) => `| ${item.id} | ${item.zh} | ${item.en} |`),
  ].join('\n');
}

function searchParameters(guidance, query) {
  const queryLower = query.trim().toLowerCase();
  const rows = [];
  for (const entry of guidance.parameters) {
    let hit = null;
    for (const term of entry.field_terms) {
      if (term.toLowerCase().includes(queryLower)) {
        hit = `现场说法：${term}`;
        break;
      }
    }
    if (hit === null && entry.zh.toLowerCase().includes(queryLower)) hit = '参数名（中文）';
    if (hit === null && entry.en.toLowerCase().includes(queryLower)) hit = '参数名（英文）';
    if (hit === null && entry.definition_zh.toLowerCase().includes(queryLower)) hit = '定义';
    if (hit !== null) {
      rows.push(`| ${entry.id} | ${entry.zh} (${entry.en}) | ${hit} |`);
    }
  }
  if (rows.length === 0) {
    return [
      `没有找到匹配“${query}”的参数候选。`,
      '可换一个现场说法重试，或运行 --list-parameters 查看全部 39 个参数。',
    ].join('\n');
  }
  return [
    `参数映射候选（只是候选，不能自动替代工程判断）：搜索词“${query}”`,
    '| 编号 | 参数 | 命中 |',
    '|---:|---|---|',
    ...rows,
    '提示：候选之间易混时，运行 --explain <编号> 查看定义和区分判据。',
  ].join('\n');
}

function explainParameter(guidance, parameterId) {
  if (!Number.isInteger(parameterId) || parameterId < 1 || parameterId > 39) {
    throw usageError(
      '参数编号超出范围',
      `--explain ${parameterId}`,
      '使用 1..39 的整数；运行 --list-parameters 查看参数表',
    );
  }
  const entry = guidance.parameters[parameterId - 1];
  const lines = [
    `参数 #${entry.id}：${entry.zh} (${entry.en})`,
    `- 定义：${entry.definition_zh}`,
    `- 现场常见说法：${entry.field_terms.join('、')}`,
    `- 可测量：${entry.measurable_zh}`,
    '- 易混参数：',
  ];
  for (const item of entry.confusable ?? []) {
    lines.push(`  - #${item.id} ${guidance.parameters[item.id - 1].zh}：${item.how}`);
  }
  return lines.join('\n');
}

function selfTest(data) {
  const known = new Map([
    ['1,28', [28, 27, 35, 26]],
    ['7,28', [25, 26, 28]],
    ['15,25', [20, 10, 28, 18]],
    ['15,31', [21, 39, 16, 22]],
    ['18,35', [15, 1, 19]],
    ['19,9', [8, 35]],
    ['1,38', [26, 35, 18, 19]],
    ['8,25', [35, 16, 32, 18]],
    ['33,10', [28, 13, 35]],
    ['34,1', [2, 27, 35, 11]],
    ['1,39', [35, 3, 24, 37]],
    ['39,1', [35, 26, 24, 37]],
    ['39,30', [22, 35, 13, 24]],
    ['39,31', [35, 22, 18, 39]],
    ['25,27', [10, 30, 4]],
    ['35,36', [15, 29, 37, 28]],
  ]);
  for (const [pair, expected] of known) {
    const [improve, worsen] = pair.split(',').map(Number);
    const actual = lookup(data, improve, worsen).principles.map((item) => item.id);
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
      throw new Error(`R${improve}C${worsen}: ${actual} != ${expected}`);
    }
  }
  if (data.parameters[29].zh !== '作用于物体的有害因素') throw new Error('Parameter #30 translation drifted');
  if (data.parameters[30].zh !== '物体产生的有害因素') throw new Error('Parameter #31 translation drifted');
  if (lookup(data, 30, 30).status !== 'physical_contradiction') throw new Error('Diagonal lookup must route to physical contradiction');
  if (lookup(data, 1, 2).status !== 'no_preferred_principle') throw new Error('Empty cell must report no_preferred_principle');
  const forward = lookup(data, 1, 39).principles.map((item) => item.id);
  const reverse = lookup(data, 39, 1).principles.map((item) => item.id);
  if (JSON.stringify(forward) === JSON.stringify(reverse)) throw new Error('Directional lookup regression');
  const guidance = loadGuidance(DEFAULT_GUIDANCE);
  if (guidance.matrix_version !== data.matrix_version) {
    throw new Error('Guidance matrix_version drifted from matrix');
  }
  return `SELF_TEST_PASS parameters=39 principles=40 rows=39 columns=39 populated=${data.audit.populated_cells} golden_cells=${known.size} matrix_sha256=${data.audit.matrix_payload_sha256}`;
}

function parseBatch(spec) {
  const tokens = spec.trim().split(/[,，;；\s]+/).filter((token) => token.length > 0);
  const pairs = [];
  for (const token of tokens) {
    const match = token.match(/^(\d+)[xX×:：](\d+)$/);
    if (!match) {
      throw usageError(
        '批量查询格式无效',
        `“${token}”`,
        '每对写成 改善x恶化 并用逗号分隔，如 --batch "1x28,39x30"',
      );
    }
    pairs.push([Number(match[1]), Number(match[2])]);
  }
  if (pairs.length === 0) {
    throw usageError('批量查询为空', `“${spec}”`, '至少一对，如 --batch "1x28"');
  }
  return pairs;
}

function parseArgs(argv) {
  const args = {format: 'markdown', data: DEFAULT_DATA, improve: null, worsen: null, list: false, selfTest: false, version: false, search: null, explain: null, batch: null};
  const unknown = [];
  const takeValue = (index, flag) => {
    const next = argv[index + 1];
    if (next === undefined || (next.startsWith('-') && !/^-\d/.test(next))) {
      throw usageError('缺少参数值', flag, `在 ${flag} 后提供一个值`);
    }
    return next;
  };
  const parseId = (flag, raw) => {
    const trimmed = raw.trim();
    if (!/^[+-]?\d+$/.test(trimmed)) {
      throw usageError(
        '参数编号无效',
        `${flag} ${raw}`,
        '使用 1..39 的整数；运行 --list-parameters 查看参数表',
      );
    }
    return Number(trimmed);
  };
  for (let i = 0; i < argv.length; i += 1) {
    let item = argv[i];
    let inlineValue = null;
    const eq = item.indexOf('=');
    if (item.startsWith('--') && eq > 0) {
      inlineValue = item.slice(eq + 1);
      item = item.slice(0, eq);
    }
    const value = (flag) => {
      if (inlineValue !== null) return inlineValue;
      const raw = takeValue(i, flag);
      i += 1;
      return raw;
    };
    if (item === '--improve') args.improve = parseId(item, value(item));
    else if (item === '--worsen') args.worsen = parseId(item, value(item));
    else if (item === '--format') args.format = value(item);
    else if (item === '--data') args.data = resolve(value(item));
    else if (item === '--list-parameters') args.list = true;
    else if (item === '--self-test') args.selfTest = true;
    else if (item === '--version') args.version = true;
    else if (item === '--search') args.search = value(item);
    else if (item === '--explain') args.explain = parseId(item, value(item));
    else if (item === '--batch') args.batch = value(item);
    else if (item === '--help' || item === '-h') {
      process.stdout.write(`${USAGE}\n`);
      process.exit(0);
    } else unknown.push(argv[i]);
  }
  if (unknown.length > 0) {
    throw usageError('未知参数', unknown.join(' '), '运行 --help 查看支持的参数');
  }
  if (!['markdown', 'json'].includes(args.format)) {
    throw usageError('参数值无效', `--format ${args.format}`, '--format 只接受 markdown 或 json');
  }
  return args;
}

try {
  const args = parseArgs(process.argv.slice(2));

  if (args.version) {
    const guidance = loadGuidance(DEFAULT_GUIDANCE);
    const data = loadResource(args.data);
    process.stdout.write(`lookup-matrix skill=${readSkillVersion()} matrix=${data.matrix_version} guidance=${guidance.guidance_version}\n`);
  } else if (args.search !== null) {
    const query = args.search.trim();
    if (!query) {
      throw usageError('搜索词为空', '--search ""', '提供一个现场说法，如 --search "看不清"');
    }
    const guidance = loadGuidance(DEFAULT_GUIDANCE);
    process.stdout.write(`${searchParameters(guidance, query)}\n`);
  } else if (args.explain !== null) {
    const guidance = loadGuidance(DEFAULT_GUIDANCE);
    process.stdout.write(`${explainParameter(guidance, args.explain)}\n`);
  } else {
    const data = loadResource(args.data);
    if (args.selfTest) {
      process.stdout.write(`${selfTest(data)}\n`);
    } else if (args.list) {
      process.stdout.write(`${renderParameters(data)}\n`);
    } else if (args.batch !== null) {
      const pairs = parseBatch(args.batch);
      const results = pairs.map(([improve, worsen]) => lookup(data, improve, worsen));
      if (args.format === 'json') {
        process.stdout.write(`${JSON.stringify(results, null, 2)}\n`);
      } else {
        const blocks = [`## 批量查询：${results.length} 对`];
        for (const result of results) {
          blocks.push(`### ${result.direction}`);
          blocks.push(renderMarkdown(result));
        }
        process.stdout.write(`${blocks.join('\n\n')}\n`);
      }
    } else {
      if (args.improve === null || args.worsen === null) {
        throw usageError(
          '缺少查询参数',
          '无 --improve/--worsen',
          '使用 --improve N --worsen N，或 --batch/--search/--explain/--list-parameters/--self-test',
        );
      }
      const result = lookup(data, args.improve, args.worsen);
      process.stdout.write(args.format === 'json' ? `${JSON.stringify(result, null, 2)}\n` : `${renderMarkdown(result)}\n`);
    }
  }
} catch (error) {
  process.stderr.write(`ERROR: ${error.message}\n`);
  process.exitCode = 2;
}
