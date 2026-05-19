/**
 * Netlify Function: upsert-override
 *
 * Recebe POST com:
 *   {
 *     senha: "<senha>",
 *     pedido_id: "...",
 *     override: { status_manual: "oculto"|"cancelado", motivo, por, data }
 *   }
 *
 * Valida senha contra process.env.SENHA_OP, lê overrides.json atual do repo,
 * adiciona/atualiza o pedido_id, e committa de volta.
 */

const GITHUB_API = 'https://api.github.com';

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 204, headers: corsHeaders(), body: '' };
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

  const { senha, pedido_id, override } = body;

  const senhaConfigurada = process.env.SENHA_OP;
  if (!senhaConfigurada) {
    return resp(500, { error: 'SENHA_OP nao configurada no Netlify' });
  }
  if (senha !== senhaConfigurada) {
    return resp(401, { error: 'Senha incorreta' });
  }

  if (!pedido_id || !override) {
    return resp(400, { error: 'pedido_id e override são obrigatórios' });
  }

  const validos = ['oculto', 'cancelado'];
  if (!validos.includes(override.status_manual)) {
    return resp(400, { error: `status_manual deve ser ${validos.join(' ou ')}` });
  }

  const token = process.env.GITHUB_TOKEN;
  const owner = process.env.GITHUB_OWNER || 'mnluizasantos-spec';
  const repo  = process.env.GITHUB_REPO  || 'lead-timev2';

  if (!token) {
    return resp(500, { error: 'GITHUB_TOKEN não configurado no Netlify' });
  }

  const apiUrl = `${GITHUB_API}/repos/${owner}/${repo}/contents/overrides.json`;

  try {
    // 1. Lê overrides.json atual
    let sha = null;
    let overrides = {};

    const getResp = await fetch(apiUrl, { headers: ghHeaders(token) });
    if (getResp.ok) {
      const fileData = await getResp.json();
      sha = fileData.sha;
      try {
        const decoded = Buffer.from(fileData.content, 'base64').toString('utf-8');
        overrides = JSON.parse(decoded);
      } catch (e) {
        // Arquivo corrompido — começa do zero
        overrides = {};
      }
    }

    // 2. Aplica o novo override
    overrides[pedido_id] = override;

    // 3. Commit de volta
    const novoJson = JSON.stringify(overrides, null, 2);
    const novoBase64 = Buffer.from(novoJson, 'utf-8').toString('base64');

    const putBody = {
      message: `chore: ${override.status_manual} pedido ${pedido_id.slice(-20)}`,
      content: novoBase64,
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
        error: `Falha ao commitar overrides.json (${putResp.status})`,
        detail: errTxt.slice(0, 500),
      });
    }

    const commit = await putResp.json();
    return resp(200, {
      ok: true,
      pedido_id,
      total_overrides: Object.keys(overrides).length,
      sha: commit.commit?.sha,
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
