#!/usr/bin/env node
/** Deterministic lookup for the bundled classical 39x39 TRIZ matrix. */

import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const DEFAULT_DATA = resolve(HERE, '..', 'references', 'contradiction-matrix.json');

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

function lookup(data, improve, worsen) {
  if (!Number.isInteger(improve) || improve < 1 || improve > 39 || !Number.isInteger(worsen) || worsen < 1 || worsen > 39) {
    throw new Error('Both parameter IDs must be integers from 1 through 39');
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
  return `SELF_TEST_PASS parameters=39 principles=40 rows=39 columns=39 populated=${data.audit.populated_cells} golden_cells=${known.size} matrix_sha256=${data.audit.matrix_payload_sha256}`;
}

function parseArgs(argv) {
  const args = {format: 'markdown', data: DEFAULT_DATA, improve: null, worsen: null, list: false, selfTest: false};
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (item === '--improve') args.improve = Number(argv[++i]);
    else if (item === '--worsen') args.worsen = Number(argv[++i]);
    else if (item === '--format') args.format = argv[++i];
    else if (item === '--data') args.data = resolve(argv[++i]);
    else if (item === '--list-parameters') args.list = true;
    else if (item === '--self-test') args.selfTest = true;
    else if (item === '--help' || item === '-h') {
      process.stdout.write('Usage: node lookup_matrix.mjs --improve N --worsen N [--format markdown|json]\n       node lookup_matrix.mjs --list-parameters\n       node lookup_matrix.mjs --self-test\n');
      process.exit(0);
    } else throw new Error(`Unknown argument: ${item}`);
  }
  if (!['markdown', 'json'].includes(args.format)) throw new Error('--format must be markdown or json');
  return args;
}

try {
  const args = parseArgs(process.argv.slice(2));
  const data = loadResource(args.data);
  if (args.selfTest) process.stdout.write(`${selfTest(data)}\n`);
  else if (args.list) process.stdout.write(`${renderParameters(data)}\n`);
  else {
    if (args.improve === null || args.worsen === null) throw new Error('--improve and --worsen are required unless --self-test or --list-parameters is used');
    const result = lookup(data, args.improve, args.worsen);
    process.stdout.write(args.format === 'json' ? `${JSON.stringify(result, null, 2)}\n` : `${renderMarkdown(result)}\n`);
  }
} catch (error) {
  process.stderr.write(`ERROR: ${error.message}\n`);
  process.exitCode = 2;
}
