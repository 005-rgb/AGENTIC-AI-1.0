// ── Config ──────────────────────────────────────────
const API = '';  // same origin
let token = localStorage.getItem('sf_token') || '';
let currentUser = null;
let currentPage = '';
let jobPollingInterval = null;
let jobPage = 1;
let currentSourceTab = 'upload';

// ── HTTP helpers ─────────────────────────────────────
async function api(method, path, body = null, isForm = false) {
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (!isForm && body) headers['Content-Type'] = 'application/json';
  const opts = { method, headers };
  if (body) opts.body = isForm ? body : JSON.stringify(body);
  const r = await fetch(API + path, opts);
  if (r.status === 204) return null;
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || data.error || r.statusText);
  return data;
}

// ── Toast ─────────────────────────────────────────────
function toast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ── Page routing ──────────────────────────────────────
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.style.display = 'none');
  const appShell = document.getElementById('app-shell');
  const authPages = ['login', 'register'];

  if (authPages.includes(name)) {
    appShell.style.display = 'none';
    const page = document.getElementById(`page-${name}`);
    if (page) page.style.display = 'flex';
  } else {
    appShell.style.display = 'flex';
    const page = document.getElementById(`page-${name}`);
    if (page) page.style.display = 'block';
    document.querySelectorAll('.sidebar-nav a').forEach(a => {
      a.classList.toggle('active', a.dataset.page === name);
    });
  }

  currentPage = name;
  stopPolling();

  if (name === 'dashboard') loadDashboard();
  if (name === 'jobs') { jobPage = 1; loadJobs(); }
  if (name === 'channels') loadChannels();
  if (name === 'keys') loadKeys();
  if (name === 'trends') {};
  if (name === 'new-job') initWizard();
}

// ── Auth ──────────────────────────────────────────────
document.getElementById('form-login').addEventListener('submit', async e => {
  e.preventDefault();
  const err = document.getElementById('login-error');
  err.style.display = 'none';
  try {
    const form = new FormData();
    form.append('username', document.getElementById('login-email').value);
    form.append('password', document.getElementById('login-password').value);
    const data = await api('POST', '/api/auth/login', form, true);
    token = data.access_token;
    localStorage.setItem('sf_token', token);
    currentUser = data.tenant;
    document.getElementById('nav-user-name').textContent = currentUser.name;
    showPage('dashboard');
  } catch (ex) {
    err.textContent = ex.message;
    err.style.display = 'block';
  }
});

document.getElementById('form-register').addEventListener('submit', async e => {
  e.preventDefault();
  const err = document.getElementById('reg-error');
  err.style.display = 'none';
  try {
    const data = await api('POST', '/api/auth/register', {
      email: document.getElementById('reg-email').value,
      password: document.getElementById('reg-password').value,
      name: document.getElementById('reg-name').value,
    });
    token = data.access_token;
    localStorage.setItem('sf_token', token);
    currentUser = data.tenant;
    document.getElementById('nav-user-name').textContent = currentUser.name;
    showPage('dashboard');
  } catch (ex) {
    err.textContent = ex.message;
    err.style.display = 'block';
  }
});

function logout() {
  token = '';
  currentUser = null;
  localStorage.removeItem('sf_token');
  showPage('login');
}

// ── Dashboard ─────────────────────────────────────────
async function loadDashboard() {
  try {
    const data = await api('GET', '/api/jobs?limit=100');
    const jobs = data.jobs || [];
    document.getElementById('stat-total').textContent = data.total || 0;
    document.getElementById('stat-done').textContent = jobs.filter(j => j.status === 'done' || j.status === 'uploaded').length;
    document.getElementById('stat-processing').textContent = jobs.filter(j => j.status === 'processing').length;
    document.getElementById('stat-scheduled').textContent = jobs.filter(j => j.status === 'scheduled').length;

    const recent = jobs.slice(0, 10);
    const el = document.getElementById('recent-jobs-table');
    if (!recent.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-icon">🎬</div><p>Belum ada job. <a href="#" onclick="showPage('new-job')">Buat job pertama</a></p></div>`;
      return;
    }
    el.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Judul/Topik</th><th>Niche</th><th>Status</th><th>Dibuat</th><th></th></tr></thead><tbody>
      ${recent.map(j => `<tr>
        <td>${j.title || j.hook_text || j.source_type || '-'}</td>
        <td>${j.niche || '-'}</td>
        <td>${statusBadge(j.status)}</td>
        <td>${fmtDate(j.created_at)}</td>
        <td><button class="btn btn-ghost btn-sm" onclick="viewJob('${j.id}')">Detail</button></td>
      </tr>`).join('')}
    </tbody></table></div>`;
  } catch (ex) { toast(ex.message, 'error'); }
}

// ── Jobs ──────────────────────────────────────────────
async function loadJobs() {
  const status = document.getElementById('job-filter-status')?.value || '';
  const limit = 20;
  try {
    const data = await api('GET', `/api/jobs?page=${jobPage}&limit=${limit}${status ? '&status=' + status : ''}`);
    const jobs = data.jobs || [];
    const el = document.getElementById('jobs-list');

    if (!jobs.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-icon">🎬</div><p>Tidak ada job${status ? ' dengan status ' + status : ''}.</p></div>`;
      return;
    }

    el.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Judul/Topik</th><th>Niche</th><th>Sumber</th><th>Status</th><th>Progress</th><th>Dibuat</th><th></th></tr></thead><tbody>
      ${jobs.map(j => `<tr>
        <td style="max-width:200px">${j.title || j.hook_text || '-'}</td>
        <td>${j.niche || '-'}</td>
        <td><span class="badge badge-pending">${j.source_type}</span></td>
        <td>${statusBadge(j.status)}</td>
        <td style="min-width:100px">
          <div class="progress-bar"><div class="progress-fill" style="width:${j.progress || 0}%"></div></div>
          <span style="font-size:11px;color:var(--text-muted)">${j.progress || 0}%</span>
        </td>
        <td>${fmtDate(j.created_at)}</td>
        <td><button class="btn btn-ghost btn-sm" onclick="viewJob('${j.id}')">Detail</button></td>
      </tr>`).join('')}
    </tbody></table></div>`;

    // Pagination
    const total = data.total || 0;
    const pages = Math.ceil(total / limit);
    const pag = document.getElementById('jobs-pagination');
    pag.innerHTML = '';
    for (let i = 1; i <= pages; i++) {
      const btn = document.createElement('button');
      btn.className = `btn btn-sm ${i === jobPage ? 'btn-primary' : 'btn-ghost'}`;
      btn.textContent = i;
      btn.onclick = () => { jobPage = i; loadJobs(); };
      pag.appendChild(btn);
    }
  } catch (ex) { toast(ex.message, 'error'); }
}

async function viewJob(jobId) {
  showPage('job-detail');
  await renderJobDetail(jobId);
  startPollingJob(jobId);
}

async function renderJobDetail(jobId) {
  try {
    const j = await api('GET', `/api/jobs/${jobId}`);
    document.getElementById('job-detail-title').textContent = j.title || j.hook_text || 'Detail Job';
    document.getElementById('job-detail-content').innerHTML = `
      <div class="detail-grid">
        <div>
          <div class="card">
            <div class="detail-meta">
              ID: ${j.id} · Dibuat: ${fmtDate(j.created_at)}
            </div>
            <div style="margin-bottom:12px">${statusBadge(j.status)} <strong>${j.progress || 0}%</strong></div>
            <div class="progress-bar" style="margin-bottom:16px"><div class="progress-fill" style="width:${j.progress || 0}%"></div></div>
            ${j.error_message ? `<div class="alert alert-error">${j.error_message}</div>` : ''}
            ${j.script ? `<div class="script-box"><h4>Script</h4><pre>${j.script}</pre></div>` : ''}
          </div>
        </div>
        <div>
          <div class="card">
            <h3 style="margin-bottom:12px">Info</h3>
            <div class="review-row"><span>Sumber</span><span>${j.source_type}</span></div>
            <div class="review-row"><span>Niche</span><span>${j.niche || '-'}</span></div>
            <div class="review-row"><span>Subtitle</span><span>${j.add_subtitles ? 'Ya' : 'Tidak'}</span></div>
            <div class="review-row"><span>Musik</span><span>${j.add_music ? 'Ya' : 'Tidak'}</span></div>
            ${j.scheduled_at ? `<div class="review-row"><span>Jadwal</span><span>${fmtDate(j.scheduled_at)}</span></div>` : ''}
            ${j.youtube_video_id ? `<div class="review-row"><span>YouTube ID</span><span><a href="https://youtu.be/${j.youtube_video_id}" target="_blank">${j.youtube_video_id}</a></span></div>` : ''}
          </div>
          <div class="card">
            <h3 style="margin-bottom:12px">Aksi</h3>
            <div class="detail-actions">
              ${j.status === 'done' ? `<a class="btn btn-primary" href="/api/jobs/${j.id}/download">⬇️ Download</a>` : ''}
              ${j.status === 'done' ? `<button class="btn btn-outline" onclick="uploadNow('${j.id}')">📤 Upload ke YouTube</button>` : ''}
              <button class="btn btn-ghost" style="color:#C0392B" onclick="deleteJob('${j.id}')">🗑️ Hapus</button>
            </div>
          </div>
        </div>
      </div>`;
  } catch (ex) { toast(ex.message, 'error'); }
}

function startPollingJob(jobId) {
  stopPolling();
  jobPollingInterval = setInterval(async () => {
    const j = await api('GET', `/api/jobs/${jobId}`).catch(() => null);
    if (!j) return;
    if (j.status === 'done' || j.status === 'failed' || j.status === 'uploaded' || j.status === 'scheduled') {
      stopPolling();
    }
    if (currentPage === 'job-detail') renderJobDetail(jobId);
  }, 3000);
}

function stopPolling() {
  if (jobPollingInterval) { clearInterval(jobPollingInterval); jobPollingInterval = null; }
}

async function uploadNow(jobId) {
  try {
    const r = await api('POST', `/api/jobs/${jobId}/upload-now`);
    toast('Upload berhasil! ID: ' + r.youtube_video_id, 'success');
    await renderJobDetail(jobId);
  } catch (ex) { toast(ex.message, 'error'); }
}

async function deleteJob(jobId) {
  if (!confirm('Hapus job ini?')) return;
  try {
    await api('DELETE', `/api/jobs/${jobId}`);
    toast('Job dihapus', 'success');
    showPage('jobs');
  } catch (ex) { toast(ex.message, 'error'); }
}

// ── New Job Wizard ────────────────────────────────────
let wizardChannels = [];

async function initWizard() {
  document.getElementById('wizard-step-1').style.display = 'block';
  document.getElementById('wizard-step-2').style.display = 'none';
  document.getElementById('wizard-step-3').style.display = 'none';
  ['wstep-1','wstep-2','wstep-3'].forEach((id, i) => {
    document.getElementById(id).className = 'step' + (i === 0 ? ' active' : '');
  });
  setSourceTab('upload');

  // Load channels
  try {
    const data = await api('GET', '/api/channels');
    wizardChannels = data.channels || [];
    const sel = document.getElementById('job-channel');
    sel.innerHTML = '<option value="">-- Tanpa channel --</option>' +
      wizardChannels.map(c => `<option value="${c.id}">${c.channel_name} (${c.niche})</option>`).join('');
  } catch(e) {}
}

function setSourceTab(tab) {
  currentSourceTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');

  if (tab === 'upload') {
    document.querySelector('.tab:nth-child(1)').classList.add('active');
    document.getElementById('tab-upload').style.display = 'block';
  } else if (tab === 'url') {
    document.querySelector('.tab:nth-child(2)').classList.add('active');
    document.getElementById('tab-url').style.display = 'block';
  } else {
    document.querySelector('.tab:nth-child(3)').classList.add('active');
    document.getElementById('tab-ai').style.display = 'block';
  }
}

function updateDropzoneLabel(input) {
  if (input.files[0]) {
    document.querySelector('.dropzone p').textContent = '✅ ' + input.files[0].name;
  }
}

function handleDrop(e) {
  e.preventDefault();
  const file = e.dataTransfer.files[0];
  if (file) {
    const input = document.getElementById('upload-file');
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    document.querySelector('.dropzone p').textContent = '✅ ' + file.name;
  }
}

function wizardNext(fromStep) {
  document.getElementById(`wizard-step-${fromStep}`).style.display = 'none';
  document.getElementById(`wizard-step-${fromStep + 1}`).style.display = 'block';
  document.getElementById(`wstep-${fromStep}`).className = 'step done';
  document.getElementById(`wstep-${fromStep + 1}`).className = 'step active';

  if (fromStep + 1 === 3) buildReview();
}

function wizardBack(fromStep) {
  document.getElementById(`wizard-step-${fromStep}`).style.display = 'none';
  document.getElementById(`wizard-step-${fromStep - 1}`).style.display = 'block';
  document.getElementById(`wstep-${fromStep}`).className = 'step';
  document.getElementById(`wstep-${fromStep - 1}`).className = 'step active';
}

function toggleScheduleInput() {
  const type = document.getElementById('job-schedule-type').value;
  document.getElementById('schedule-custom-field').style.display = type === 'custom' ? 'block' : 'none';
}

function buildReview() {
  const niche = document.getElementById('job-niche').value;
  const hook = document.getElementById('job-hook').value;
  const schedule = document.getElementById('job-schedule-type').value;
  const platforms = [...document.querySelectorAll('.checkbox-grid input:checked')].map(c => c.value);

  let sourceLabel = '';
  if (currentSourceTab === 'upload') {
    const f = document.getElementById('upload-file').files[0];
    sourceLabel = f ? f.name : '(belum pilih file)';
  } else if (currentSourceTab === 'url') {
    sourceLabel = document.getElementById('source-url').value || '-';
  } else {
    sourceLabel = document.getElementById('ai-topic').value || '-';
  }

  document.getElementById('review-summary').innerHTML = `
    <div class="review-row"><span>Sumber</span><span>${currentSourceTab}</span></div>
    <div class="review-row"><span>File/URL/Topik</span><span style="word-break:break-all;max-width:250px">${sourceLabel}</span></div>
    <div class="review-row"><span>Niche</span><span>${niche || '-'}</span></div>
    <div class="review-row"><span>Hook Text</span><span>${hook || '-'}</span></div>
    <div class="review-row"><span>Subtitle</span><span>${document.getElementById('job-subtitles').checked ? 'Ya' : 'Tidak'}</span></div>
    <div class="review-row"><span>Musik</span><span>${document.getElementById('job-music').checked ? 'Ya' : 'Tidak'}</span></div>
    <div class="review-row"><span>Jadwal</span><span>${schedule}</span></div>
    <div class="review-row"><span>Platform</span><span>${platforms.join(', ') || 'youtube'}</span></div>
  `;
}

async function submitJob() {
  const btn = document.getElementById('btn-submit-job');
  const errEl = document.getElementById('submit-error');
  errEl.style.display = 'none';
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Memproses...';

  try {
    const niche = document.getElementById('job-niche').value;
    const hook = document.getElementById('job-hook').value;
    const channelId = document.getElementById('job-channel').value;
    const subtitles = document.getElementById('job-subtitles').checked;
    const music = document.getElementById('job-music').checked;
    const schedType = document.getElementById('job-schedule-type').value;
    const platforms = [...document.querySelectorAll('.checkbox-grid input:checked')].map(c => c.value);
    let scheduledAt = null;
    if (schedType === 'custom') scheduledAt = document.getElementById('job-schedule-at').value;

    let jobId;

    if (currentSourceTab === 'upload') {
      const file = document.getElementById('upload-file').files[0];
      if (!file) throw new Error('Pilih file terlebih dahulu');
      const fd = new FormData();
      fd.append('file', file);
      fd.append('source_type', 'upload');
      fd.append('niche', niche);
      fd.append('hook_text', hook);
      fd.append('channel_id', channelId);
      fd.append('add_subtitles', subtitles);
      fd.append('add_music', music);
      fd.append('platforms', JSON.stringify(platforms));
      if (scheduledAt) fd.append('scheduled_at', scheduledAt);
      const r = await api('POST', '/api/jobs', fd, true);
      jobId = r.job_id;
    } else {
      const body = {
        source_type: currentSourceTab === 'url' ? 'url' : 'text_to_shorts',
        source_url: currentSourceTab === 'url' ? document.getElementById('source-url').value : null,
        niche: currentSourceTab === 'text_to_shorts' ? document.getElementById('ai-niche').value : niche,
        hook_text: currentSourceTab === 'text_to_shorts' ? document.getElementById('ai-topic').value : hook,
        channel_id: channelId || null,
        add_subtitles: subtitles,
        add_music: music,
        platforms,
        scheduled_at: scheduledAt,
      };
      const r = await api('POST', '/api/jobs/json', body);
      jobId = r.job_id;
    }

    toast('Job berhasil dibuat! 🚀', 'success');
    viewJob(jobId);
  } catch (ex) {
    errEl.textContent = ex.message;
    errEl.style.display = 'block';
    btn.disabled = false;
    btn.innerHTML = '🚀 Mulai Proses';
  }
}

async function loadTrendsForWizard() {
  const niche = document.getElementById('ai-niche').value;
  const el = document.getElementById('wizard-trends');
  el.style.display = 'block';
  el.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Memuat tren...</p>';
  try {
    const data = await api('GET', `/api/trends?niche=${niche}&limit=5`);
    el.innerHTML = (data.trends || []).map(t => `
      <div class="trend-item" style="cursor:pointer" onclick="document.getElementById('ai-topic').value='${t.topic.replace(/'/g,"\\'")}';toast('Topik dipilih!','success')">
        <div><div class="trend-topic">${t.topic}</div><div class="trend-hook">${t.suggested_hook}</div></div>
        <div class="trend-score">${t.score}</div>
      </div>`).join('');
  } catch (ex) {
    el.innerHTML = `<div class="alert alert-error">${ex.message}</div>`;
  }
}

// ── Channels ──────────────────────────────────────────
async function loadChannels() {
  try {
    const data = await api('GET', '/api/channels');
    const el = document.getElementById('channels-list');
    const channels = data.channels || [];
    if (!channels.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-icon">📺</div><p>Belum ada channel. Tambah channel untuk mulai upload otomatis.</p></div>`;
      return;
    }
    el.innerHTML = channels.map(c => `
      <div class="channel-card">
        <div class="channel-info">
          <div class="channel-name">📺 ${c.channel_name}</div>
          <div class="channel-niche">${c.niche} · ${c.has_youtube_auth ? '✅ Terhubung YouTube' : '⚠️ Belum terhubung'}</div>
        </div>
        <div class="channel-actions">
          ${!c.has_youtube_auth ? `<button class="btn btn-outline btn-sm" onclick="connectYoutube('${c.id}')">🔗 Connect YouTube</button>` : ''}
          <button class="btn btn-ghost btn-sm" style="color:#C0392B" onclick="deleteChannel('${c.id}')">Hapus</button>
        </div>
      </div>`).join('');
  } catch (ex) { toast(ex.message, 'error'); }
}

function showAddChannelModal() {
  document.getElementById('modal-content').innerHTML = `
    <h3 style="margin-bottom:20px">Tambah Channel</h3>
    <div class="field"><label>Nama Channel</label><input type="text" id="m-channel-name" placeholder="Nama channel YouTube"/></div>
    <div class="field"><label>Niche</label>
      <select id="m-channel-niche">
        ${['motivasi','edukasi','humor','fakta','tutorial','lifestyle','finance','kesehatan','teknologi','lainnya']
          .map(n => `<option value="${n}">${n}</option>`).join('')}
      </select>
    </div>
    <div id="m-channel-err" class="alert alert-error" style="display:none"></div>
    <div style="display:flex;gap:10px;margin-top:16px">
      <button class="btn btn-primary" onclick="addChannel()">Simpan</button>
      <button class="btn btn-ghost" onclick="closeModal()">Batal</button>
    </div>`;
  document.getElementById('modal-overlay').style.display = 'flex';
}

async function addChannel() {
  const err = document.getElementById('m-channel-err');
  err.style.display = 'none';
  try {
    await api('POST', '/api/channels', {
      channel_name: document.getElementById('m-channel-name').value,
      niche: document.getElementById('m-channel-niche').value,
    });
    closeModal();
    toast('Channel ditambahkan!', 'success');
    loadChannels();
  } catch (ex) {
    err.textContent = ex.message;
    err.style.display = 'block';
  }
}

async function connectYoutube(channelId) {
  try {
    const r = await api('GET', `/api/channels/${channelId}/oauth-url`);
    window.open(r.auth_url, '_blank');
    toast('Halaman Google OAuth dibuka di tab baru', 'info');
  } catch (ex) { toast(ex.message, 'error'); }
}

async function deleteChannel(channelId) {
  if (!confirm('Hapus channel ini?')) return;
  try {
    await api('DELETE', `/api/channels/${channelId}`);
    toast('Channel dihapus', 'success');
    loadChannels();
  } catch (ex) { toast(ex.message, 'error'); }
}

// ── Gemini Keys ───────────────────────────────────────
async function loadKeys() {
  try {
    const data = await api('GET', '/api/keys');
    const banner = document.getElementById('pool-banner');
    const pool = data.pool_size || 0;
    const total = data.total || 0;
    banner.className = `pool-banner alert ${pool === 0 ? 'alert-error' : 'alert-success'}`;
    banner.textContent = pool === 0
      ? '⚠️ Pool kosong! Tambahkan minimal 1 API key aktif untuk mulai memproses.'
      : `✅ Pool aktif: ${pool} dari ${total} key siap digunakan`;

    const el = document.getElementById('keys-table');
    if (!data.keys.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-icon">🔑</div><p>Belum ada API key. Tambahkan Gemini API key untuk mengaktifkan fitur AI.</p></div>`;
      return;
    }
    el.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Label</th><th>API Key</th><th>Status</th><th>Penggunaan</th><th>Terakhir Dipakai</th><th></th></tr></thead><tbody>
      ${data.keys.map(k => `<tr class="${k.is_active ? '' : 'key-inactive'}">
        <td>${k.label || '-'}</td>
        <td><code style="font-size:12px">${k.api_key}</code></td>
        <td><span class="badge ${k.is_active ? 'badge-done' : 'badge-failed'}">${k.is_active ? 'Aktif' : 'Nonaktif'}</span></td>
        <td>${k.usage_count || 0}x</td>
        <td>${k.last_used_at ? fmtDate(k.last_used_at) : '-'}</td>
        <td style="display:flex;gap:6px">
          <button class="btn btn-ghost btn-sm" onclick="toggleKey('${k.id}')">${k.is_active ? 'Nonaktifkan' : 'Aktifkan'}</button>
          <button class="btn btn-ghost btn-sm" style="color:#C0392B" onclick="deleteKey('${k.id}')">Hapus</button>
        </td>
      </tr>`).join('')}
    </tbody></table></div>`;
  } catch (ex) { toast(ex.message, 'error'); }
}

async function addKey() {
  const keyVal = document.getElementById('new-key-value').value.trim();
  const label = document.getElementById('new-key-label').value.trim();
  if (!keyVal) { toast('Masukkan API key', 'error'); return; }
  try {
    await api('POST', '/api/keys', { api_key: keyVal, label });
    document.getElementById('new-key-value').value = '';
    document.getElementById('new-key-label').value = '';
    toast('Key ditambahkan!', 'success');
    loadKeys();
  } catch (ex) { toast(ex.message, 'error'); }
}

async function testNewKey() {
  const keyVal = document.getElementById('new-key-value').value.trim();
  if (!keyVal) { toast('Masukkan API key terlebih dahulu', 'error'); return; }
  const el = document.getElementById('key-test-result');
  el.innerHTML = '<span style="color:var(--text-muted);font-size:13px">Testing...</span>';
  try {
    const r = await api('POST', '/api/keys/test', { api_key: keyVal });
    el.innerHTML = r.valid
      ? `<div class="alert alert-success">✅ Key valid! Model: ${r.model}</div>`
      : `<div class="alert alert-error">❌ Key tidak valid: ${r.error}</div>`;
  } catch (ex) { el.innerHTML = `<div class="alert alert-error">Error: ${ex.message}</div>`; }
}

async function toggleKey(keyId) {
  try {
    await api('POST', `/api/keys/${keyId}/toggle`);
    loadKeys();
  } catch (ex) { toast(ex.message, 'error'); }
}

async function deleteKey(keyId) {
  if (!confirm('Hapus API key ini?')) return;
  try {
    await api('DELETE', `/api/keys/${keyId}`);
    toast('Key dihapus', 'success');
    loadKeys();
  } catch (ex) { toast(ex.message, 'error'); }
}

// ── Trends ────────────────────────────────────────────
async function loadTrends() {
  const niche = document.getElementById('trend-niche').value;
  const el = document.getElementById('trends-list');
  el.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-muted)">🔍 Mencari tren...</div>';
  try {
    const data = await api('GET', `/api/trends?niche=${niche}&limit=10`);
    const trends = data.trends || [];
    if (!trends.length) {
      el.innerHTML = `<div class="alert alert-info">Tidak ada tren ditemukan untuk niche "${niche}"</div>`;
      return;
    }
    el.innerHTML = trends.map(t => `
      <div class="trend-item">
        <div style="flex:1">
          <div class="trend-topic">${t.topic}</div>
          <div class="trend-hook" style="margin-top:4px">💬 ${t.suggested_hook}</div>
          ${t.why_trending ? `<div class="trend-hook">📈 ${t.why_trending}</div>` : ''}
        </div>
        <div style="display:flex;flex-direction:column;align-items:center;gap:8px">
          <div class="trend-score">${t.score}</div>
          <button class="btn btn-outline btn-sm" onclick="useAsTopic('${t.topic.replace(/'/g,"\\'")}')">Pakai</button>
        </div>
      </div>`).join('');
  } catch (ex) { el.innerHTML = `<div class="alert alert-error">${ex.message}</div>`; }
}

function useAsTopic(topic) {
  document.getElementById('script-topic').value = topic;
  toast('Topik dimasukkan ke form script!', 'success');
}

async function generateScript() {
  const topic = document.getElementById('script-topic').value.trim();
  const niche = document.getElementById('script-niche').value;
  const duration = parseInt(document.getElementById('script-duration').value);
  if (!topic) { toast('Masukkan topik terlebih dahulu', 'error'); return; }

  const el = document.getElementById('script-result');
  el.style.display = 'block';
  el.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-muted)">🤖 Generating script...</div>';

  try {
    const data = await api('POST', '/api/trends/generate-script', { topic, niche, duration_seconds: duration });
    el.innerHTML = `
      <div class="script-box"><h4>Judul A</h4><pre>${data.title || ''}</pre></div>
      <div class="script-box"><h4>Judul B (A/B Test)</h4><pre>${data.title_variant_b || ''}</pre></div>
      <div class="script-box"><h4>Hook</h4><pre>${data.hook || ''}</pre></div>
      <div class="script-box"><h4>Script Lengkap</h4><pre>${data.full_script || ''}</pre></div>
      <div class="script-box"><h4>Deskripsi</h4><pre>${data.description || ''}</pre></div>
      <div style="margin-top:10px">
        <strong>Tags:</strong> ${(data.tags || []).map(t => `<span class="badge badge-pending">${t}</span>`).join(' ')}
      </div>
      <div style="margin-top:8px">
        <strong>Hook Options:</strong><br>
        ${(data.hook_options || []).map((h, i) => `<div style="font-size:13px;padding:4px 0">${i+1}. ${h}</div>`).join('')}
      </div>`;
  } catch (ex) { el.innerHTML = `<div class="alert alert-error">${ex.message}</div>`; }
}

// ── Modal ─────────────────────────────────────────────
function closeModal() { document.getElementById('modal-overlay').style.display = 'none'; }

// ── Helpers ───────────────────────────────────────────
function statusBadge(status) {
  const map = { pending:'badge-pending', processing:'badge-processing', done:'badge-done', scheduled:'badge-scheduled', uploaded:'badge-uploaded', failed:'badge-failed' };
  return `<span class="badge ${map[status] || 'badge-pending'}">${status}</span>`;
}

function fmtDate(d) {
  if (!d) return '-';
  return new Date(d).toLocaleString('id-ID', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' });
}

// ── Init ──────────────────────────────────────────────
(async () => {
  if (token) {
    try {
      const me = await api('GET', '/api/auth/me');
      currentUser = me;
      document.getElementById('nav-user-name').textContent = me.name;
      showPage('dashboard');
    } catch {
      token = '';
      localStorage.removeItem('sf_token');
      showPage('login');
    }
  } else {
    showPage('login');
  }
})();
