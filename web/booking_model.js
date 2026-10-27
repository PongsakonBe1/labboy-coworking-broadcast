/* ค่าภายในคงตาม monitor; แปลงคำสำหรับผู้ใช้เมื่อแสดงผลเท่านั้น */
(function (root) {
  function statusLabel(status) {
    return status === 'หมดเวลา' ? 'ครบเวลาแล้ว' : status;
  }
  function selectBookings(rows, room = 'all', status = 'all', sort = 'priority') {
    const result = rows.filter(row => (room === 'all' || row.room === room) &&
      (status === 'all' || row.status === status || statusLabel(row.status) === status));
    const rank = row => row.status === 'กำลังใช้ห้อง' || row.alert === 'กำลังส่งเสียง…' ? 0 :
      row.status === 'จองแล้ว' || row.status === 'เช็คอินแล้ว' ? 1 : 2;
    return result.sort((a, b) => {
      if (sort !== 'start') {
        const group = rank(a) - rank(b);
        if (group) return group;
        if (rank(a) === 2) return b.end.localeCompare(a.end);
        return (rank(a) === 1 ? a.start.localeCompare(b.start) : a.end.localeCompare(b.end));
      }
      return a.start.localeCompare(b.start);
    });
  }
  function roomStatusKind(room) {
    if (room.status_kind === 'red' || room.status.includes('ไม่สำเร็จ')) return 'red';
    if (room.status_kind === 'green' || room.status.includes('สำเร็จ')) return 'green';
    return room.status_kind === 'amber' ? 'amber' : 'neutral';
  }
  function alertLabel(row) {
    const alert = row.alert || '';
    if (alert.includes('ไม่สำเร็จ')) return `! ${alert}`;
    if (alert === 'ส่งเสียงแล้ว') return `✓ ${alert}`;
    if (alert.startsWith('ข้าม')) return `– ${alert}`;
    if (row.status === 'กำลังใช้ห้อง' && (!alert || alert === 'รอตรวจสถานะ')) return 'กำลังใช้ · รอหมดเวลา';
    if (row.status === 'จองแล้ว' && (!alert || alert === 'รอเริ่มใช้งาน')) return 'รอเวลาเริ่มใช้งาน';
    return alert || 'รอตรวจสถานะ';
  }
  const model = {statusLabel, selectBookings, roomStatusKind, alertLabel};
  if (typeof module !== 'undefined' && module.exports) module.exports = model;
  else root.BookingModel = model;
})(typeof window === 'undefined' ? globalThis : window);
