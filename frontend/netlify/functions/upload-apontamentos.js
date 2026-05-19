/**
 * Netlify Function: upload-apontamentos
 *
 * Recebe POST com:
 *   { senha: "FILTROSOP", filename: "apontamentos.xlsx", content_base64: "..." }
 *
 * Valida senha, então usa a API do GitHub pra commitar (substituir)
 * o arquivo `apontamentos.xlsx` no repo lead-timev2.
 *
 * Environment variables necessárias no Netlify:
 *   GITHUB_TOKEN  → Personal Access Token com permissão de write no repo
 *   GITHUB_OWNER  → mnluizasantos-spec
 *   GITHUB_REPO   → lead-timev2
 *   SENHA_OP      → FILTROSOP (a senha pode ser sobreescrita aqui)
 */

const GITHUB_API = 'https://api.github.com';

exports.handler = async (event) => {
  // CORS pré-flight
  if (event.httpMethod === 'OPTIONS') {
    return {
      statusCode: 204,
      headers: corsHeaders(),
      body: '',
    };
  }

  if (event.httpMethod !== 'POST') {
    return resp(405, { error: 'Method Not Allowed' });
  }

  let body;
  try {
    body = JSON.parse(event.body);
  } catch (e) {
    return resp(400, { error: 'JSON inválido' });
  }

  const { senha, filename, content_base64 } = body;

  // Validações
  const senhaCorreta = process.env.SENHA_OP || 'FILTROSOP';
  if (senha !== senhaCorreta) {
    return resp(401, { error: 'Senha incorreta' });
  }

  if (!filename || !/^apontamentos\.(xlsx?|csv)$/i.test(filename)) {
    return resp(400, { error: 'filename deve ser apontamentos.xlsx/xls/csv' });
  }

  if (!content_base64 || content_base64.length < 100) {
    return resp(400, { error: 'content_base64 vazio ou muito pequeno' });
  }

  // Limita a 25 MB (Netlify Functions tem 6 MB de payload máximo,
  // mas content_base64 em si pode ser maior. 25MB ~ 33MB em base64.)
  if (content_base64.length > 35 * 1048576) {
    return resp(400, { error: 'Arquivo > 25MB. Reduza ou exporte com menos linhas.' });
  }

  const token = process.env.GITHUB_TOKEN;
  const owner = process.env.GITHUB_OWNER || 'mnluizasantos-spec';
  const repo  = process.env.GITHUB_REPO  || 'lead-timev2';

  if (!token) {
    return resp(500, { error: 'GITHUB_TOKEN não configurado no Netlify' });
  }

  const apiUrl = `${GITHUB_API}/repos/${owner}/${repo}/contents/${filename}`;

  try {
    // 1. Pega SHA atual do arquivo (se existir) pra poder substituir
    let sha = null;
    const getResp = await fetch(apiUrl, {
      headers: ghHeaders(token),
    });
    if (getResp.ok) {
      const fileData = await getResp.json();
      sha = fileData.sha;
    }

    // 2. PUT pra commitar
    const putBody = {
      message: `chore: atualizar ${filename} via dashboard`,
      content: content_base64,
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
