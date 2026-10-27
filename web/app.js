/**
 * LabBoy Coworking Broadcast - WebView Controller Frontend
 */

const $ = (id) => document.getElementById(id);
let current = null;
let roomsSignature = '';
let bookingsSignature = '';
let activitySignature = '';
let toastTimer = null;
let isSettingsView = false;
let settingsDirty = false;
let dismissedAlert = '';
let refreshPending = false;

const THAI_DAYS = ['วันอาทิตย์', 'วันจันทร์', 'วันอังคาร', 'วันพุธ', 'วันพฤหัสบดี', 'วันศุกร์', 'วันเสาร์'];
const THAI_MONTHS = [
  'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
  'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม'
];

function formatThaiDateTime(dateObj) {
  const day = THAI_DAYS[dateObj.getDay()];
  const date = dateObj.getDate();
  const month = THAI_MONTHS[dateObj.getMonth()];
  const year = dateObj.getFullYear() + 543;
  const hours = String(dateObj.getHours()).padStart(2, '0');
  const minutes = String(dateObj.getMinutes()).padStart(2, '0');
  const seconds = String(dateObj.getSeconds()).padStart(2, '0');
  return `${day}ที่ ${date} ${month} ${year}  ${hours}:${minutes}:${seconds}`;
}

function formatThaiDateOnly(dateObj) {
  const day = THAI_DAYS[dateObj.getDay()];
  const date = dateObj.getDate();
  const month = THAI_MONTHS[dateObj.getMonth()];
  const year = dateObj.getFullYear() + 543;
  return `${day}ที่ ${date} ${month} ${year}`;
}

const esc = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));

const api = () => window.pywebview?.api;

async function call(name, ...args) {
  if (!api()) throw new Error('กำลังเชื่อมต่อหน้าควบคุม...');
  return await api()[name](...args);
}

function notify(text) {
  const el = $('toast');
  if (!el) return;
  el.textContent = text;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3000);
}

function showNotice(title, message) {
  $('noticeTitle').textContent = title;
  $('noticeMessage').textContent = message;
  $('noticeDialog').showModal();
}

function showConfirm(title, message, action = 'ยืนยัน', tone = 'primary') {
  return new Promise((resolve) => {
    const dialog = $('confirmDialog');
    const button = $('confirmButton');
    $('confirmTitle').textContent = title;
    $('confirmMessage').textContent = message;
    button.textContent = action;
    button.className = `button ${tone}`;

    const handleClose = (e) => {
      if (e.target !== dialog) return;
      dialog.removeEventListener('close', handleClose);
      resolve(dialog.returnValue === 'confirm');
    };

    dialog.returnValue = '';
    dialog.addEventListener('close', handleClose);
    dialog.showModal();
  });
}

window.showCloseConfirm = async () => {
  const accepted = await showConfirm(
    'หยุดและปิดโปรแกรมหรือไม่',
    'ระบบกำลังตรวจตารางอยู่ การปิดโปรแกรมจะหยุดการประกาศเสียงอัตโนมัติ',
    'หยุดและปิด',
    'warning'
  );
  if (accepted) {
    await call('confirm_exit');
  }
};

function setStatus(text, kind = 'blue') {
  $('statusText').textContent = text;
  $('statusPill').className = `system-pill ${kind}`;
}

function reuseRows(container, items, tagName) {
  // เก็บ widget/DOM เดิมไว้ อัปเดตเฉพาะแถวที่เปลี่ยนและย้ายตำแหน่งเมื่อจำเป็น.
  if (!container._rowPool) {
    container._rowPool = new Map();
    container.replaceChildren();
  }
  const visible = new Set(items.map(item => item.key));
  for (const [key, node] of container._rowPool) node.hidden = !visible.has(key);
  let previous = null;
  for (const item of items) {
    let node = container._rowPool.get(item.key);
    if (!node) {
      node = document.createElement(tagName);
      container._rowPool.set(item.key, node);
    }
    node.hidden = false;
    node.className = item.className || '';
    if (node._content !== item.html) {
      node.innerHTML = item.html;
      node._content = item.html;
    }
    const anchor = previous ? previous.nextSibling : container.firstChild;
    if (anchor !== node) container.insertBefore(node, anchor);
    previous = node;
  }
}

/* ------------------- Render Sidebar Room Cards ------------------- */
function renderRooms(cards) {
  const signature = JSON.stringify(cards);
  if (signature === roomsSignature) return;
  roomsSignature = signature;

  const container = $('roomCardsList');
  if (!container) return;

  container.innerHTML = cards.map((room) => {
    const statusClass = BookingModel.roomStatusKind(room);

    const tintBg = room.tint || '#EAF3FF';
    const tintColor = room.tint_text || '#0055B8';

    return `
      <article class="room-card">
        <div class="room-card-top">
          <span class="room-card-icon" style="background:${esc(tintBg)}; color:${esc(tintColor)};">
            <svg viewBox="0 0 24 24"><path d="M4 10v4h4l5 4V6l-5 4H4Z"/><path d="M16 9a5 5 0 0 1 0 6"/></svg>
          </span>
          <h3 class="room-card-title">${esc(room.name)}</h3>
          <span class="room-card-badge">ROOM ${esc(room.number)}</span>
        </div>
        <div class="room-card-meta">
          <span class="room-ip-text">${esc(room.ip || 'ยังไม่ตั้งค่า IP')}</span>
          <span class="room-status-pill ${statusClass}">
            ● ${esc(room.status)}
          </span>
        </div>
        <div class="room-card-actions">
          <button class="test-speaker-btn" data-room="${esc(room.name)}" title="ทดสอบส่งเสียงไปยังลำโพง 1 ครั้ง">
            <svg viewBox="0 0 24 24"><path d="M4 10v4h4l5 4V6l-5 4H4Z"/><path d="M16 9a5 5 0 0 1 0 6"/></svg>
            ทดสอบเสียง 1 ครั้ง
          </button>
          <button class="detail-btn" data-detail="${esc(room.name)}">รายละเอียด</button>
        </div>
      </article>
    `;
  }).join('');

  container.querySelectorAll('[data-room]').forEach((btn) => {
    btn.onclick = () => testRoom(btn.dataset.room);
  });

  container.querySelectorAll('[data-detail]').forEach((btn) => {
    btn.onclick = () => showRoomDetail(btn.dataset.detail, cards);
  });

  // อัปเดตตัวเลือกใน Filter dropdown
  const filterSelect = $('roomFilter');
  if (filterSelect) {
    const prev = filterSelect.value;
    filterSelect.innerHTML = '<option value="all">ทุกห้อง</option>' +
      cards.map((r) => `<option value="${esc(r.name)}">${esc(r.name)}</option>`).join('');
    filterSelect.value = cards.some((r) => r.name === prev) ? prev : 'all';
  }
}

function showRoomDetail(roomName, cards) {
  const room = cards.find((r) => r.name === roomName);
  if (!room) return;
  $('roomDetailTitle').textContent = `ห้อง ${room.name} (ROOM ${room.number})`;
  $('roomDetailContent').innerHTML = `
    <div class="room-detail-row"><span>ชื่อห้อง:</span><span>${esc(room.name)}</span></div>
    <div class="room-detail-row"><span>หมายเลขห้อง:</span><span>ROOM ${esc(room.number)}</span></div>
    <div class="room-detail-row"><span>IP Address:</span><span>${esc(room.ip || 'ยังไม่กำหนด')}</span></div>
    <div class="room-detail-row"><span>Audio ID:</span><span>${esc(room.audio_id || '13')}</span></div>
    <div class="room-detail-row"><span>สถานะล่าสุด:</span><span>${esc(room.status)}</span></div>
  `;
  $('roomDetailDialog').showModal();
}

/* ------------------- Render Bookings Table ------------------- */
function renderBookings(rows) {
  const roomFilter = $('roomFilter')?.value || 'all';
  const statusFilter = $('statusFilter')?.value || 'all';
  const sortFilter = $('sortFilter')?.value || 'priority';

  const filtered = BookingModel.selectBookings(rows, roomFilter, statusFilter, sortFilter);

  const signature = JSON.stringify(filtered);
  if (signature === bookingsSignature) return;
  bookingsSignature = signature;

  const tbody = $('bookingRows');
  if (!tbody) return;

  if (!filtered.length) {
    reuseRows(tbody, [{key:'empty',html:'<td colspan="4" class="empty-state">ไม่พบรายการตามตัวกรอง</td>'}], 'tr');
    return;
  }

  const renderedRows = filtered.map((row) => {
    let badgeHtml = '';
    let alertHtml = esc(BookingModel.alertLabel(row));

    if (row.status === 'กำลังใช้ห้อง') {
      badgeHtml = '<span class="badge badge-green">● กำลังใช้ห้อง</span>';
      if (!row.alert || row.alert === 'รอตรวจสถานะ') {
        const eta = current?.next_broadcast && current.next_broadcast.room === row.room
          ? ` (อีก ${current.next_broadcast.eta})` : '';
        alertHtml = `กำลังใช้ · รอหมดเวลา${eta}`;
      }
    } else if (row.status === 'จองแล้ว') {
      badgeHtml = '<span class="badge badge-blue">● จองแล้ว</span>';
      if (!row.alert || row.alert === 'รอเริ่มใช้งาน') {
        alertHtml = 'รอเวลาเริ่มใช้งาน';
      }
    } else if (row.status === 'เช็คอินแล้ว') {
      badgeHtml = '<span class="badge badge-blue">● เช็คอินแล้ว</span>';
    } else if (row.status === 'ระงับการจอง' || row.status === 'ไม่ทราบสถานะ') {
      badgeHtml = `<span class="badge badge-red">! ${esc(row.status)}</span>`;
    } else {
      if (row.alert && row.alert.includes('ส่งเสียงแล้ว')) {
        badgeHtml = '<span class="badge badge-gray">✓ ครบเวลาแล้ว</span>';
      } else if (row.alert && (row.alert.includes('ข้าม') || row.alert.includes('ระงับ'))) {
        badgeHtml = '<span class="badge badge-gray">– ครบเวลาแล้ว</span>';
      } else {
        badgeHtml = '<span class="badge badge-gray">● ครบเวลาแล้ว</span>';
      }
    }

    const rowClass = row.status === 'กำลังใช้ห้อง' ? 'booking-active' :
      row.alert?.startsWith('ข้าม') ? 'booking-skipped' : row.alert === 'ส่งเสียงแล้ว' ? 'booking-sent' : '';
    return {key:row.key, className:rowClass, html:`
        <td>
          <span class="room-cell-name">${esc(row.room)}</span>
          <span class="room-cell-sub">ROOM ${esc(row.room_number)}</span>
        </td>
        <td class="booking-time-cell">${esc(row.start)}–${esc(row.end)}</td>
        <td>${badgeHtml}</td>
        <td title="${esc(row.alert)}">${alertHtml}</td>
    `};
  });
  reuseRows(tbody, renderedRows, 'tr');
}

/* ------------------- Render Timeline Activity ------------------- */
function renderActivity(items) {
  const signature = JSON.stringify(items);
  if (signature === activitySignature) return;
  activitySignature = signature;

  const container = $('timelineList');
  if (!container) return;

  if (!items || !items.length) {
    reuseRows(container, [{key:'empty',html:'<div class="empty-state">ยังไม่มีกิจกรรม</div>'}], 'div');
    return;
  }

  reuseRows(container, items.slice(0, 40).map((item, index) => ({key:`event-${index}`,html:`
    <div class="timeline-row">
      <i class="timeline-dot ${esc(item.kind)}"></i>
      <div>
        <div class="timeline-title">${esc(item.title)}</div>
        <div class="timeline-subtitle">${esc(item.subtitle)}</div>
      </div>
      <time class="timeline-time">${esc(item.time)}</time>
    </div>
  `})), 'div');
}

/* ------------------- Alert Banner ------------------- */
function setAlert(state) {
  const message = state.auth_error ? 'รหัสผ่านลำโพงไม่ผ่านการตรวจสอบ' : state.read_error || '';
  const banner = $('alertBanner');
  if (!banner) return;

  if (!message) dismissedAlert = '';
  banner.classList.toggle('hidden', !message || message === dismissedAlert);
  banner.classList.toggle('amber', !state.auth_error);
  $('alertText').textContent = message;
  $('alertAction').textContent = state.auth_error ? 'แก้รหัสลำโพง' : (message ? 'เปิดบันทึก Log' : '');
  $('alertAction').onclick = () => (state.auth_error ? openPassword() : call('open_logs'));
}

/* ------------------- Master Update Loop ------------------- */
function update(state) {
  current = state;
  const now = new Date();

  // นาฬิกาและวันที่
  $('clockDate').textContent = state.now.slice(0, 10);
  $('clockTime').textContent = state.now.slice(11);
  $('todayDateLabel').textContent = formatThaiDateOnly(now);

  setStatus(state.status, state.status_kind);
  $('statusText').title = state.status;
  document.documentElement.dataset.theme = state.settings.appearance || 'light';

  // สวิตช์โหมด
  $('liveSwitch').checked = state.is_live;
  $('liveSwitch').disabled = state.running;
  $('liveSwitch').closest('label').title = state.running
    ? 'หยุดระบบก่อนเปลี่ยนโหมด เพื่อให้โหมดตรงกับการทำงานจริง'
    : 'สลับโหมดใช้งานจริง / โหมดทดลอง';

  // ปุ่มควบคุมการทำงานหลัก (สลับระหว่าง "หยุดชั่วคราว" และ "ทำงานต่อ")
  const actionBtn = $('topActionBtn');
  if (state.running) {
    actionBtn.textContent = 'หยุดชั่วคราว';
    actionBtn.className = 'button warning small-btn';
  } else {
    actionBtn.textContent = state.status.includes('หยุด') ? 'ทำงานต่อ' : 'เริ่มตรวจตาราง';
    actionBtn.className = state.status.includes('หยุด') ? 'button success small-btn' : 'button primary small-btn';
  }

  // เสียงรอบถัดไป + แถบสถิติ
  if (state.next_broadcast) {
    $('nextTitle').textContent = `เสียงรอบถัดไป: ห้อง ${state.next_broadcast.room} (ROOM ${state.next_broadcast.room_number}) · ${state.next_broadcast.detail}`;
    $('nextTitle').title = $('nextTitle').textContent;
    $('nextEtaBadge').textContent = `อีก ${state.next_broadcast.eta}`;
  } else {
    $('nextTitle').textContent = state.is_live
      ? 'เสียงรอบถัดไป: ยังไม่มีรายการที่รอหมดเวลา'
      : 'โหมดทดลอง: ตรวจตารางโดยไม่ส่งคำสั่งลำโพง';
    $('nextEtaBadge').textContent = state.last_read === 'ยังไม่อ่าน' ? 'รออ่านตาราง' : `อ่านล่าสุด ${state.last_read}`;
  }

  $('runtimeStat').textContent = state.metrics.runtime;
  $('readsStat').textContent = `${state.metrics.reads} รอบ`;
  $('bookingsStat').textContent = `${state.metrics.bookings} รายการ`;
  $('successStat').textContent = `${state.metrics.successes} สำเร็จ`;
  $('failureStat').textContent = `${state.metrics.failures} ไม่สำเร็จ`;
  $('failureStat').classList.toggle('failure-count', state.metrics.failures > 0);

  // เรนเดอร์การ์ดห้อง, ตาราง และกิจกรรม
  renderRooms(state.room_cards);
  renderBookings(state.bookings);
  renderActivity(state.activities);
  setAlert(state);

  // เติมข้อมูลหน้าตั้งค่า
  if (!settingsDirty) fillSettings(state.settings);
}

function fillSettings(settings) {
  if (!settings) return;
  if ($('passwordStatusDesc')) {
    $('passwordStatusDesc').textContent = settings.has_password
      ? 'บันทึกใน Windows แล้ว'
      : 'ยังไม่ได้บันทึกรหัสผ่าน (กรุณากำหนดก่อนเริ่มงานจริง)';
  }
  if ($('startupCheckbox')) $('startupCheckbox').checked = !!settings.startup_enabled;
  if ($('trayCheckbox')) $('trayCheckbox').checked = !!settings.close_to_tray;
  $('sidebarStartup').checked = !!settings.startup_enabled;
  $('sidebarTray').checked = !!settings.close_to_tray;
  $('appearanceSelect').value = settings.appearance || 'light';
  if ($('settingsScheduleUrl') && document.activeElement !== $('settingsScheduleUrl')) {
    $('settingsScheduleUrl').value = settings.schedule_url || '';
  }

  const container = $('roomEditList');
  if (container && !container.dataset.initialized) {
    container.dataset.initialized = 'true';
    container.innerHTML = (settings.rooms || []).map((r) => roomEditorRow(r)).join('');
    bindRoomEditEvents();
  }
}

function roomEditorRow(room = { name: '', number: '', ip: '', audio_id: 13 }) {
  return `
    <div class="room-edit-row">
      <input aria-label="ชื่อห้อง" placeholder="ชื่อห้อง" data-field="name" value="${esc(room.name)}">
      <input aria-label="เลขห้อง" placeholder="เลขห้อง" data-field="number" value="${esc(room.number)}">
      <input aria-label="IP" placeholder="IP address" data-field="ip" value="${esc(room.ip)}">
      <input aria-label="Audio ID" type="number" min="1" max="128" data-field="audio_id" value="${esc(room.audio_id)}">
      <button type="button" class="room-del-btn" aria-label="ลบห้อง">×</button>
    </div>
  `;
}

function bindRoomEditEvents() {
  $('roomEditList')?.querySelectorAll('.room-del-btn').forEach((btn) => {
    btn.onclick = () => { settingsDirty = true; btn.closest('.room-edit-row').remove(); };
  });
}

function getRoomPayload() {
  const rows = [...$('roomEditList').querySelectorAll('.room-edit-row')];
  return rows.map((row) =>
    Object.fromEntries(
      [...row.querySelectorAll('[data-field]')].map((input) => [
        input.dataset.field,
        input.dataset.field === 'audio_id' ? Number(input.value) : input.value.trim()
      ])
    )
  );
}

async function refresh() {
  if (refreshPending) return;
  refreshPending = true;
  try {
    update(await call('get_state'));
  } catch (error) {
    setStatus('เชื่อมต่อหน้าควบคุมไม่ได้', 'red');
  } finally {
    refreshPending = false;
  }
}

/* ------------------- การสลับ View ระหว่าง Main / Settings ------------------- */
function toggleView() {
  isSettingsView = !isSettingsView;
  $('mainView').classList.toggle('hidden', isSettingsView);
  $('settingsView').classList.toggle('hidden', !isSettingsView);

  const btnText = $('viewToggleText');
  const btnIcon = $('viewToggleIcon');
  if (isSettingsView) {
    btnText.textContent = 'กลับหน้าหลัก';
    btnIcon.textContent = '←';
  } else {
    btnText.textContent = 'ตั้งค่า';
    btnIcon.textContent = '⚙';
  }
}

/* ------------------- การสั่งงาน ------------------- */
async function handleActionClick() {
  if (current?.running) {
    const ok = await showConfirm(
      'หยุดระบบชั่วคราว?',
      'ระหว่างหยุด ระบบจะไม่ตรวจตารางและไม่มีการประกาศเสียง',
      'หยุดชั่วคราว',
      'warning'
    );
    if (!ok) return;
    await call('pause_monitor');
    setTimeout(refresh, 600);
  } else {
    if (current?.is_live && !current.settings.has_password) {
      openPassword();
      return;
    }
    const ok = await showConfirm(
      current?.is_live ? 'เริ่มระบบประกาศเสียงจริง?' : 'เริ่มตรวจตารางแบบทดลอง?',
      'ระบบจะเริ่มอ่านตาราง K‑Room ทันที' + (current?.is_live ? ' และสั่งเสียงเมื่อรายการที่เข้าเงื่อนไขครบเวลา' : ''),
      'เริ่มตรวจตาราง',
      current?.is_live ? 'success' : 'primary'
    );
    if (!ok) return;
    try {
      const result = await call('start_monitor');
      if (!result.ok && result.needs_password) {
        openPassword();
        return;
      }
      if (!result.ok) showNotice('เริ่มระบบไม่ได้', result.message || 'เกิดข้อผิดพลาด');
      await refresh();
    } catch (error) {
      showNotice('เริ่มระบบไม่ได้', String(error));
    }
  }
}

async function handleModeChange() {
  if (!current) return;
  const wanted = $('liveSwitch').checked ? 'ใช้งานจริง' : 'ทดลอง';
  if (current.running) {
    $('liveSwitch').checked = current.is_live;
    return;
  }
  if (wanted === 'ใช้งานจริง') {
    const ok = await showConfirm(
      'เปิดโหมดใช้งานจริง?',
      'เมื่อเริ่มตรวจ ระบบจะส่งคำสั่งไปยังลำโพงจริงเมื่อรายการจองที่กำลังใช้งานครบเวลา',
      'เปิดโหมดจริง',
      'success'
    );
    if (!ok) {
      $('liveSwitch').checked = false;
      return;
    }
  }
  try {
    const result = await call('set_mode', wanted);
    if (!result.ok) {
      showNotice('เปลี่ยนโหมดไม่ได้', result.message);
      $('liveSwitch').checked = current.is_live;
      return;
    }
    update(result.state);
    if (wanted === 'ใช้งานจริง' && !current.settings.has_password) {
      openPassword();
    }
  } catch (error) {
    showNotice('เปลี่ยนโหมดไม่ได้', String(error));
  }
}

async function testRoom(room) {
  let warningNote = '';
  if (current?.running && current.next_broadcast && Number(current.next_broadcast.seconds) < 120) {
    warningNote = `\n\nคำเตือน: เหลือเวลาเพียง ${current.next_broadcast.eta} ก่อนรอบประกาศถัดไป`;
  }

  const ok = await showConfirm(
    `ทดสอบเสียงห้อง ${room}?`,
    `จะสั่งเล่นเสียงทดสอบ 1 ครั้งที่ห้อง ${room}${current?.monitor_running ? '\n\nระบบจะหยุดตรวจตารางชั่วคราว และจะเริ่มตรวจต่อให้อัตโนมัติหลังเล่นเสียงเสร็จ' : ''}${warningNote}`,
    'ทดสอบเสียง',
    'primary'
  );
  if (!ok) return;

  try {
    const result = await call('test_speaker', room);
    if (result.needs_password) {
      openPassword();
      return;
    }
    if (!result.ok) {
      showNotice('ทดสอบเสียงไม่ได้', result.message || 'ไม่สามารถสั่งเล่นเสียงได้');
    } else {
      notify(result.message || `กำลังส่งเสียงทดสอบไปยังห้อง ${room}...`);
    }
    await refresh();
  } catch (error) {
    showNotice('ทดสอบเสียงไม่ได้', String(error));
  }
}

function openPassword() {
  $('passwordInput').value = '';
  $('passwordDialog').showModal();
  $('passwordInput').focus();
}

async function savePasswordSubmit(e) {
  e.preventDefault();
  const password = $('passwordInput').value;
  let restart = false;
  $('passwordDialog').close();
  if (current?.monitor_running) {
    restart = await showConfirm('ใช้รหัสใหม่ทันที?',
      'เลือกใช้ทันทีเพื่อหยุดแล้วเริ่มระบบด้วยรหัสใหม่ หรือยกเลิกเพื่อใช้เมื่อเริ่มตรวจครั้งถัดไป',
      'บันทึกและใช้ทันที', 'primary');
  }
  try {
    const result = await call('save_password', password, restart);
    $('passwordInput').value = '';
    if (!result.ok) {
      showNotice('บันทึกรหัสไม่ได้', result.message || 'โปรดตรวจสอบรหัสผ่าน');
    } else {
      notify(result.message || 'บันทึกรหัสผ่านใน Windows แล้ว');
    }
    await refresh();
  } catch (error) {
    showNotice('บันทึกรหัสไม่ได้', String(error));
  }
}

async function saveSettingsSubmit(optionsOnly = false) {
  try {
    const payload = {
      schedule_url: optionsOnly ? current.settings.schedule_url : $('settingsScheduleUrl').value,
      startup_enabled: $('startupCheckbox').checked,
      close_to_tray: $('trayCheckbox').checked,
      appearance: $('appearanceSelect').value,
      ...(optionsOnly ? {} : {rooms: getRoomPayload()})
    };
    const result = await call('save_settings', payload);
    if (!result.ok) {
      showNotice('บันทึกการตั้งค่าไม่ได้', result.message);
      return;
    }
    notify(result.message);
    if (!optionsOnly) settingsDirty = false;
    roomsSignature = '';
    await refresh();
  } catch (error) {
    showNotice('บันทึกการตั้งค่าไม่ได้', String(error));
  }
}

/* ------------------- Bind UI Events ------------------- */
function bindEvents() {
  $('viewToggleBtn').onclick = toggleView;
  $('topActionBtn').onclick = handleActionClick;
  $('liveSwitch').onchange = handleModeChange;
  $('topPasswordBtn').onclick = openPassword;
  $('settingsManagePasswordBtn').onclick = openPassword;

  $('saveRoomConfigBtn').onclick = () => saveSettingsSubmit();
  $('startupCheckbox').onchange = () => saveSettingsSubmit(true);
  $('trayCheckbox').onchange = () => saveSettingsSubmit(true);
  $('sidebarStartup').onchange = () => { $('startupCheckbox').checked = $('sidebarStartup').checked; saveSettingsSubmit(true); };
  $('sidebarTray').onchange = () => { $('trayCheckbox').checked = $('sidebarTray').checked; saveSettingsSubmit(true); };
  $('appearanceSelect').onchange = () => {
    document.documentElement.dataset.theme = $('appearanceSelect').value;
    saveSettingsSubmit(true);
  };
  $('settingsScheduleUrl').oninput = () => { settingsDirty = true; };
  $('roomEditList').oninput = () => { settingsDirty = true; };

  $('addRoomBtn').onclick = () => {
    settingsDirty = true;
    $('roomEditList').insertAdjacentHTML('beforeend', roomEditorRow());
    bindRoomEditEvents();
  };

  $('clearActivityBtn').onclick = async () => {
    await call('clear_activity');
    activitySignature = '';
    refresh();
  };
  $('openLogsBtn').onclick = () => call('open_logs');

  $('roomFilter').onchange = () => { bookingsSignature = ''; if (current) renderBookings(current.bookings); };
  $('statusFilter').onchange = () => { bookingsSignature = ''; if (current) renderBookings(current.bookings); };
  $('sortFilter').onchange = () => { bookingsSignature = ''; if (current) renderBookings(current.bookings); };

  $('dismissAlert').onclick = () => { dismissedAlert = $('alertText').textContent; $('alertBanner').classList.add('hidden'); };
  $('showPasswordToggle').onclick = () => {
    const input = $('passwordInput');
    const isPassword = input.type === 'password';
    input.type = isPassword ? 'text' : 'password';
    $('showPasswordToggle').textContent = isPassword ? 'ซ่อน' : 'แสดง';
  };

  $('passwordForm').onsubmit = savePasswordSubmit;

  document.querySelectorAll('[data-close]').forEach((btn) => {
    btn.onclick = () => $(btn.dataset.close).close();
  });
}

window.addEventListener('pywebviewready', async () => {
  bindEvents();
  try {
    const state = await call('startup');
    update(state);
    setInterval(refresh, 1000);
    if (state.status === 'ตั้งรหัสลำโพงก่อนเริ่มระบบ' && !state.settings.has_password) {
      openPassword();
    }
  } catch (error) {
    showNotice('เปิดหน้าควบคุมไม่ได้', String(error));
  }
});
