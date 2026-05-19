/**
 * Netlify Function: upload-apontamentos
 *
 * Recebe POST com:
 *   {
 *     senha: "<senha>",
 *     filename: "apontamentos.xlsx",
 *     content_base64_gz: "<base64 do arquivo comprimido com gzip>",
 *     size_original: <bytes do arquivo original, pra validação>
 *   }
 *
 * Valida senha, descomprime o gzip, valida o magic header do xlsx,
 * e committa no GitHub via API REST (PUT contents).
 *
 * Environment variables necessárias no Netlify:
 *   GITHUB_TOKEN  → Personal Access Token com permissão de write no repo
 *   GITHUB_OWNER  → mnluizasantos-spec (default)
 *   GITHUB_REPO   → lead-timev2 (default)
 *   SENHA_OP      → senha exigida pra fazer upload
 */
const zlib = require('zlib');

const GITHUB_API = 'https://api.github.com';
const TAMANHO_MIN_BYTES = 10 * 1024;      // 10 KB (arquivo válido tem que ter pelo menos isso)
const TAMANHO_MAX_BYTES = 50 * 1048576;   // 50 MB descomprimido

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 204, headers: corsHeaders(), body: '' };
  }
  if (event.httpMethod !== 'POST') {
    return resp(405, { error: 'Method Not Allowed' });
  }

  // Parse do body
  let body;
  try {
    body = JSON.parse(event.body);
  } catch (e) {
    return resp(400, { error: 'JSON invalido' });
  }

  const { senha, filename, content_base64_gz, size_original } = body;

  // Validação da senha
  const senhaConfigurada = process.env.SENHA_OP;
  if (!senhaConfigurada) {
    return resp(500, { error: 'SENHA_OP nao configurada no Netlify' });
  }
  if (senha !== senhaConfigurada) {
    return resp(401, { error: 'Senha incorreta' });
  }

  // Validação do filename
  if (!filename || !/^apontamentos\.(xlsx?|csv)$/i.test(filename)) {
    return resp(400, { error: 'filename deve ser apontamentos.xlsx/xls/csv' });
  }

  // Validação do conteúdo
  if (!content_base64_gz || content_base64_gz.length < 100) {
    return resp(400, { error: 'content_base64_gz vazio ou muito pequeno' });
  }

  // Descomprime
  let bytes;
  try {
    const comprimido = Buffer.from(content_base64_gz, 'base64');
    bytes = zlib.gunzipSync(comprimido);
  } catch (e) {
    return resp(400, { error: 'Falha ao descomprimir gzip', detail: e.message });
  }

  // Valida tamanho
  if (bytes.length < TAMANHO_MIN_BYTES) {
    return resp(400, { error: `Arquivo muito pequeno (${bytes.length} bytes) — provavelmente corrompido` });
  }
  if (bytes.length > TAMANHO_MAX_BYTES) {
    return resp(400, { error: `Arquivo muito grande (${(bytes.length/1048576).toFixed(1)} MB > 50 MB)` });
  }

  // Valida que size_original bate (se foi informado)
  if (size_original && Math.abs(bytes.length - size_original) > 10) {
    return resp(400, {
      error: 'Tamanho descomprimido nao bate com original',
      esperado: size_original,
      recebido: bytes.length,
    });
  }

  // Valida que parece CSV (primeira linha tem 'data' e 'codproduto')
  // Lê só os primeiros 500 bytes pra inspecionar header
  if (filename.toLowerCase().endsWith('.csv')) {
    const header = bytes.slice(0, 500).toString('utf-8').toLowerCase();
    if (!header.includes('data') || !header.includes('codproduto')) {
      return resp(400, {
        error: 'CSV nao parece ser apontamentos (faltam colunas data/codproduto)',
        primeiros_chars: bytes.slice(0, 200).toString('utf-8'),
      });
    }
  }

  // Verificação do token GitHub
  const token = process.env.GITHUB_TOKEN;
  const owner = process.env.GITHUB_OWNER || 'mnluizasantos-spec';
  const repoNome = process.env.GITHUB_REPO || 'lead-timev2';

  if (!token) {
    return resp(500, { error: 'GITHUB_TOKEN nao configurado no Netlify' });
  }

  const apiUrl = `${GITHUB_API}/repos/${owner}/${repoNome}/contents/${filename}`;

  try {
    // 1. Pega SHA atual (se existir) pra substituir
    let sha = null;
    const getResp = await fetch(apiUrl, { headers: ghHeaders(token) });
    if (getResp.ok) {
      const fileData = await getResp.json();
      sha = fileData.sha;
    }

    // 2. Re-encoda em base64 (pro GitHub API) e committa
    const contentBase64 = bytes.toString('base64');

    const putBody = {
      message: `chore: atualizar ${filename} via dashboard (${(bytes.length/1048576).toFixed(2)} MB)`,
      content: contentBase64,
      committer: {
        name: 'Lead Time Dashboard',
        email: 'dashboard@antilhas.local',
      },
    };
    if (sha) putBody.sha = sha;

    const putResp = await fetch(apiUrl, {
      method: 'PUT',
      headers: ghHeaders(token),
      body: JSON.stringify(putBody),
    });

    if (!putResp.ok) {
      const errTxt = await putResp.text();
      return resp(500, {
        error: `Falha ao commitar no GitHub (${putResp.status})`,
        detail: errTxt.slice(0, 500),
      });
    }

    const commit = await putResp.json();
    return resp(200, {
      ok: true,
      filename,
      tamanho_bytes: bytes.length,
      tamanho_mb: (bytes.length / 1048576).toFixed(2),
      sha: commit.commit?.sha || commit.content?.sha,
      url: commit.content?.html_url,
    });

  } catch (e) {
    return resp(500, { error: 'Erro inesperado', detail: e.message });
  }
};

function ghHeaders(token) {
  return {
    'Accept': 'application/vnd.github+json',
    'Authorization': `Bearer ${token}`,
    'User-Agent': 'lead-time-dashboard',
    'Content-Type': 'application/json',
  };
}

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
}

function resp(status, body) {
  return {
    statusCode: status,
    headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}
