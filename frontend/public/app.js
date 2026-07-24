let API_BASE = window.location.origin
if (window.location.hostname.includes('github.io')) {
  API_BASE = 'https://data-agents-i94s.onrender.com';
}
let currentRole = localStorage.getItem('upa.role') || 'officer'
let csvTables = []
let dbProfiles = []

const $ = (sel) => document.querySelector(sel)
const $$ = (sel) => Array.from(document.querySelectorAll(sel))

/* ---------- Navigation ---------- */

function switchView(name) {
  $$('.nav-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.view === name)
  })
  $$('.view').forEach((view) => {
    view.classList.toggle('active', view.id === `view-${name}`)
  })
  if (name === 'data') loadCsvTables()
  if (name === 'connections') loadProfiles()
}

/* ---------- Role Toggle ---------- */

function setRole(role) {
  currentRole = role
  localStorage.setItem('upa.role', role)
  $$('.role-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.role === role)
  })
}

/* ---------- Chat ---------- */

function appendMessage({ role, text, meta, chart, table_data }) {
  const area = $('#chatArea')

  // Remove welcome card if present
  const welcome = area.querySelector('.welcome-card')
  if (welcome) welcome.remove()

  const msg = document.createElement('div')
  msg.className = `message ${role}`

  const avatar = document.createElement('div')
  avatar.className = 'avatar'
  avatar.textContent = role === 'user' ? '🧑‍💼' : '🤖'

  const bubble = document.createElement('div')
  bubble.className = 'bubble'

  const content = document.createElement('div')
  content.className = 'msg-content markdown-body'
  
  if (window.marked && text) {
    content.innerHTML = marked.parse(text)
  } else {
    content.textContent = text
  }
  bubble.appendChild(content)

  // Render Data Table
  if (table_data && table_data.columns && table_data.rows) {
     const tableWrapper = document.createElement('div')
     tableWrapper.className = 'data-table-wrapper'
     
     const table = document.createElement('table')
     table.className = 'data-table'
     
     // Headers
     const thead = document.createElement('thead')
     const trHead = document.createElement('tr')
     table_data.columns.forEach(col => {
       const th = document.createElement('th')
       th.textContent = col
       trHead.appendChild(th)
     })
     thead.appendChild(trHead)
     table.appendChild(thead)
     
     // Body
     const tbody = document.createElement('tbody')
     table_data.rows.forEach(row => {
       const tr = document.createElement('tr')
       table_data.columns.forEach(col => {
         const td = document.createElement('td')
         td.textContent = row[col] !== null ? row[col] : ''
         tr.appendChild(td)
       })
       tbody.appendChild(tr)
     })
     table.appendChild(tbody)
     tableWrapper.appendChild(table)
     bubble.appendChild(tableWrapper)
  }
  
  // Render Chart
  if (chart && chart.type && window.Chart) {
    const canvasWrapper = document.createElement('div')
    canvasWrapper.className = 'chart-wrapper'
    const canvas = document.createElement('canvas')
    canvasWrapper.appendChild(canvas)
    bubble.appendChild(canvasWrapper)
    
    setTimeout(() => {
        new Chart(canvas, {
          type: chart.type === 'bar' ? 'bar' : chart.type,
          data: {
            labels: chart.x || [],
            datasets: [{
              label: chart.ylabel || 'Value',
              data: chart.y || [],
              backgroundColor: 'rgba(54, 162, 235, 0.6)',
              borderColor: 'rgba(54, 162, 235, 1)',
              borderWidth: 1
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              title: {
                display: !!chart.title,
                text: chart.title
              }
            }
          }
        })
    }, 10)
  }

  if (meta) {
    const m = document.createElement('div')
    m.className = 'meta'
    m.textContent = meta
    bubble.appendChild(m)
  }

  msg.appendChild(avatar)
  msg.appendChild(bubble)
  area.appendChild(msg)
  area.scrollTop = area.scrollHeight
}

function setLoading(loading) {
  $('#sendBtn').disabled = loading
  $('#questionInput').disabled = loading
  if (loading) {
    $('#sendBtn').innerHTML = '<span>Sending…</span>'
  } else {
    $('#sendBtn').innerHTML = `
      <span>Send</span>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <line x1="22" y1="2" x2="11" y2="13"></line>
        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
      </svg>
    `
  }
}

async function sendQuestion(question) {
  appendMessage({ role: 'user', text: question })
  setLoading(true)

  try {
    const startRes = await fetch(`${API_BASE}/runs/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, role: currentRole }),
    })

    const startData = await startRes.json()
    if (!startRes.ok) {
      const msg =
        (startData?.error && String(startData.error)) ||
        (startData?.data?.error && String(startData.data.error)) ||
        `Request failed: ${startRes.status}`
      appendMessage({ role: 'assistant', text: `⚠️ ${msg}` })
      return
    }

      let runId = startData?.data?.run_id || startData?.run_id
      
      const startStatus = startData?.data?.status || startData?.status
      if (startStatus === 'completed' || startStatus === 'failed') {
        const out = startData?.data?.output || startData?.output || ''
        const chart = startData?.data?.chart || startData?.chart
        const table_data = startData?.data?.table_data || startData?.table_data
        const err = startData?.data?.error || startData?.error || ''
        
        appendMessage({
          role: 'assistant',
          text: startStatus === 'failed' ? `❌ ${err || 'Run failed.'}` : out || `${startStatus}`,
          meta: `Run #${runId}`,
          chart: chart,
          table_data: table_data
        })
        return
      }

      appendMessage({
        role: 'assistant',
        text: '⏳ Processing your request…',
        meta: `Run #${runId}`,
      })

      // Poll for completion
      let terminal = false
      for (let i = 0; i < 120 && !terminal; i += 1) {
       await new Promise((r) => setTimeout(r, 1000))
       const statusRes = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}`)
       if (!statusRes.ok) continue
       const statusJson = await statusRes.json()
        const status =
          (statusJson?.data?.status && String(statusJson.data.status)) ||
          (statusJson?.status && String(statusJson.status)) ||
          'unknown'

        if (['completed', 'failed', 'timeout'].includes(status)) {
          terminal = true
          const out =
            statusJson?.data?.output_text ||
            statusJson?.data?.output ||
            statusJson?.output ||
            ''
          const err =
            statusJson?.data?.error_message ||
            statusJson?.data?.error ||
            statusJson?.error ||
            ''
          appendMessage({
            role: 'assistant',
            text: status === 'failed' ? `❌ ${err || 'Run failed.'}` : out || `${status}`,
            meta: `Run #${runId}`,
          })
        }
      }
  } catch (e) {
    appendMessage({ role: 'assistant', text: `⚠️ ${e.message}` })
  } finally {
    setLoading(false)
  }
}

function submitChat(ev) {
  ev.preventDefault()
  const input = $('#questionInput')
  const question = (input?.value || '').trim()
  if (!question) return
  input.value = ''
  sendQuestion(question)
}

/* ---------- CSV Upload ---------- */

async function uploadCsv(file) {
  if (!file) return
  const zone = $('#uploadZone')
  const feedback = $('#uploadFeedback')

  // UI: loading state
  zone.classList.add('uploading')
  zone.classList.remove('success', 'error')
  feedback.className = 'upload-feedback loading visible'
  feedback.textContent = `Uploading ${file.name}…`

  try {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${API_BASE}/runs/upload-csv`, {
      method: 'POST',
      body: form,
    })
    const data = await res.json()
    if (!res.ok) {
      throw new Error(
        data?.error ||
        (data?.data && data.data.error) ||
        `Upload failed: ${res.status}`,
      )
    }

    const meta = data?.data || data
    const first = Array.isArray(meta?.uploaded) ? meta.uploaded[0] : null
    const rows = first?.rows ?? '?'
    const cols = (first?.columns || []).length

    // UI: success state
    zone.classList.remove('uploading')
    zone.classList.add('success')
    feedback.className = 'upload-feedback success visible'
    feedback.textContent = `✓ Loaded: ${first?.table_name || file.name} — ${rows} rows, ${cols} columns`

    // Reset after delay
    setTimeout(() => {
      zone.classList.remove('success')
      feedback.classList.remove('visible')
      $('#csvInput').value = ''
    }, 4000)

    loadCsvTables()
    return meta
  } catch (e) {
    // UI: error state
    zone.classList.remove('uploading')
    zone.classList.add('error')
    feedback.className = 'upload-feedback error visible'
    feedback.textContent = `✗ Upload failed: ${e.message}`

    setTimeout(() => {
      zone.classList.remove('error')
      feedback.classList.remove('visible')
    }, 6000)
    throw e
  }
}

/* ---------- CSV Tables ---------- */

async function loadCsvTables() {
  try {
    const res = await fetch(`${API_BASE}/runs/csv-tables`)
    if (!res.ok) return
    const data = await res.json()
    const tables = data?.data?.tables || []
    csvTables = tables
    renderCsvTables(tables)
  } catch (e) {
    // silent
  }
}

async function deleteCsvTable(tableName) {
  if (!confirm(`Remove table "${tableName}"? The data will be deleted from memory.`)) return
  const res = await fetch(
    `${API_BASE}/runs/csv-tables/${encodeURIComponent(tableName)}`,
    { method: 'DELETE' },
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const msg = body?.error?.message || body?.message || `Delete failed (${res.status})`
    alert(msg)
    return
  }
  loadCsvTables()
}

function renderCsvTables(tables) {
  const list = $('#csvTables')
  list.innerHTML = ''

  if (tables.length === 0) {
    list.innerHTML = `
      <div class="empty-state">
        <span class="empty-icon">📭</span>
        <p>No tables loaded yet.</p>
        <p class="empty-hint">Upload a CSV to get started.</p>
      </div>
    `
    return
  }

  tables.forEach((t) => {
    const li = document.createElement('li')
    li.className = 'table-chip'
    const displayName = t.filename || t.table_name
    li.innerHTML = `
      <span class="table-name" title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</span>
      <span class="table-meta">${t.rows ?? '?'} rows</span>
      <button class="delete-btn" data-table="${escapeHtml(t.table_name)}" title="Delete table">🗑</button>
    `
    li.querySelector('.delete-btn').addEventListener('click', () => deleteCsvTable(t.table_name))
    list.appendChild(li)
  })
}

/* ---------- Database Profiles ---------- */

async function saveDbProfile(ev) {
  ev.preventDefault()
  const fd = new FormData(ev.target)
  const payload = Object.fromEntries(fd.entries())
  payload.trust_server_certificate = !!payload.trust_server_certificate

  const res = await fetch(`${API_BASE}/runs/db-profile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await res.json()
  if (!res.ok) {
    alert(data?.error || `Save failed: ${res.status}`)
    return
  }
  ev.target.reset()
  loadProfiles()
}

async function loadProfiles() {
  try {
    const res = await fetch(`${API_BASE}/runs/db-profiles`)
    if (!res.ok) return
    const data = await res.json()
    dbProfiles = data?.data || []
    renderProfiles(dbProfiles)
  } catch (e) {
    // silent
  }
}

function renderProfiles(profiles) {
  const list = $('#profileList')
  list.innerHTML = ''

  if (!profiles.length) {
    list.innerHTML = `
      <div class="empty-state">
        <span class="empty-icon">🔌</span>
        <p>No saved connections.</p>
        <p class="empty-hint">Add a connection to query live databases.</p>
      </div>
    `
    return
  }

  profiles.forEach((p) => {
    const li = document.createElement('li')
    li.className = 'profile-card'
    li.innerHTML = `
      <div class="profile-info">
        <strong>${escapeHtml(p.name || 'Profile')}</strong>
        <span>${escapeHtml(p.server || '')} · ${escapeHtml(p.database || '')}</span>
      </div>
      <button class="delete-btn" data-id="${p.id}">Delete</button>
    `
    li.querySelector('.delete-btn').addEventListener('click', () => deleteProfile(p.id))
    list.appendChild(li)
  })
}

async function deleteProfile(id) {
  if (!confirm('Delete this connection profile?')) return
  const res = await fetch(`${API_BASE}/runs/db-profile/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    alert(`Delete failed: ${res.status}`)
    return
  }
  loadProfiles()
}

/* ---------- Utilities ---------- */

function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/* ---------- Wiring ---------- */

function wire() {
  // Navigation
  $$('.nav-btn').forEach((btn) =>
    btn.addEventListener('click', () => switchView(btn.dataset.view)),
  )

  // Role toggle
  $$('.role-btn').forEach((btn) =>
    btn.addEventListener('click', () => setRole(btn.dataset.role)),
  )

  // Chat form
  $('#chatForm')?.addEventListener('submit', submitChat)

  // CSV upload
  $('#csvInput')?.addEventListener('change', async (ev) => {
    const file = ev.target.files?.[0]
    if (!file) return
    try {
      await uploadCsv(file)
    } catch (e) {
      // error already shown in UI
    }
  })

  // DB form
  $('#dbForm')?.addEventListener('submit', saveDbProfile)
}

// Initialize
wire()
setRole(currentRole)
loadCsvTables()
loadProfiles()
