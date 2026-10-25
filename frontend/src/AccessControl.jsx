import { useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import ModalDialog from "./components/ModalDialog";
import { useConfirm } from "./components/ConfirmDialog";
import { deleteRoom, fetchAccessRecords, fetchAdminBusinesses, fetchAdminRecords, fetchMyAccessHistory,
  fetchMyRooms, grantRoomAccess, grantRoomAccessBulk, revokeRoomAccess, saveRoom, unlockRoom } from "./api";

const BASE = "/dashboard/access-control";
const SECTION_TITLES = { rooms: "Rooms & Doors", permissions: "Access Permissions", history: "Access History" };
const DEVICE_STATUS = { not_configured: "Hardware not configured", online: "Online", offline: "Offline" };
const ADMIN_SOURCES = { rooms: "rooms", grants: "room-access-grants", changes: "room-permission-changes", history: "room-access-history" };
const EMPLOYER_SOURCES = { rooms: "rooms", grants: "grants", changes: "permission-changes", history: "history" };
const emptyRoom = { name: "", building: "", floor: "", door_identifier: "" };

const dateTime = (value) => value ? new Date(value).toLocaleString() : "Not recorded";
const floorName = (floor) => /^\d+$/.test(floor) ? `Floor ${floor}` : floor;
const unique = (values) => [...new Set(values)].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
function load(token, role, kind, business) {
  if (role === "employee") return kind === "rooms" ? fetchMyRooms(token) : fetchMyAccessHistory(token);
  if (role === "admin") return fetchAdminRecords(token, ADMIN_SOURCES[kind], business ? { business } : {});
  return fetchAccessRecords(token, EMPLOYER_SOURCES[kind]);
}

// Only an expired session signs the user out; a refused request just shows its message.
function useAccessRecords(token, role, kind, business, onAuthError) {
  const [state, setState] = useState({ rows: [], loading: true, error: "" });
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let cancelled = false;
    load(token, role, kind, business)
      .then((rows) => { if (!cancelled) setState({ rows, loading: false, error: "" }); })
      .catch((err) => {
        if (cancelled) return;
        setState((current) => ({ ...current, loading: false, error: err.message }));
        if (err.status === 401) onAuthError?.(err);
      });
    return () => { cancelled = true; };
  }, [token, role, kind, business, version, onAuthError]);
  const reload = useCallback(() => setVersion((value) => value + 1), []);
  return { ...state, reload };
}

function DoorIcon() {
  return <svg className="room-door" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M6 21V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v17M4 21h16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    <circle cx="14.6" cy="12.4" r="1.1" fill="currentColor" />
  </svg>;
}

function Heading({ title, description, action }) {
  return <div className="section-heading"><div><p className="eyebrow dark-eyebrow">ACCESS CONTROL</p><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</div>;
}

function Messages({ error, notice }) {
  return <>
    {error && <p className="message error" role="alert">{error}</p>}
    {notice && <p className="message success" role="status">{notice}</p>}
  </>;
}

function Table({ columns, rows, empty, actions }) {
  if (!rows.length) return <p className="empty-state">{empty}</p>;
  return <div className="table-scroll"><table>
    <thead><tr>{columns.map((column) => <th key={column.title} scope="col">{column.title}</th>)}{actions && <th scope="col">Actions</th>}</tr></thead>
    <tbody>{rows.map((row) => <tr key={row.id}>
      {columns.map((column) => <td key={column.title}>{column.render(row)}</td>)}
      {actions && <td><div className="row-actions">{actions(row)}</div></td>}
    </tr>)}</tbody>
  </table></div>;
}

function Person({ name, email }) {
  return <span>{name}{email && <small className="muted"> {email}</small>}</span>;
}

// --- Rooms & Doors --------------------------------------------------------------

function RoomForm({ token, room, currentCheckInDoor, onClose, onSaved }) {
  const [form, setForm] = useState(room ? { name: room.name, building: room.building, floor: room.floor, door_identifier: room.door_identifier, is_check_in_door: room.is_check_in_door } : { ...emptyRoom, is_check_in_door: false });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, confirmation] = useConfirm();
  const bind = (name) => ({ id: `room-${name}`, name, value: form[name], required: true,
    onChange: (event) => setForm((current) => ({ ...current, [name]: event.target.value })) });

  async function submit(event) {
    event.preventDefault();
    if (form.is_check_in_door && currentCheckInDoor && currentCheckInDoor.id !== room?.id && !await confirm({
      title: "Replace check-in door?",
      message: `${currentCheckInDoor.name} is currently the official check-in door. Replace it with ${form.name}?`,
      confirmLabel: "Replace check-in door",
    })) return;
    setBusy(true);
    setError("");
    try { onSaved(await saveRoom(token, form, room?.id)); } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  return <ModalDialog title={room ? "Edit room" : "Add a room"} onClose={onClose}>
    <form className="record-form" onSubmit={submit}><fieldset disabled={busy}>
      {error && <p className="message error" role="alert">{error}</p>}
      <div className="record-fields">
        <div><label htmlFor="room-name">Room name or number</label><input {...bind("name")} maxLength="100" placeholder="Room 101" /></div>
        <div><label htmlFor="room-door_identifier">Door / device identifier</label><input {...bind("door_identifier")} maxLength="100" placeholder="DOOR-101" /></div>
        <div><label htmlFor="room-building">Building</label><input {...bind("building")} maxLength="100" placeholder="Main Building" /></div>
        <div><label htmlFor="room-floor">Floor</label><input {...bind("floor")} maxLength="30" placeholder="1" /></div>
        <div className="field-wide room-attendance-choice">
          <label htmlFor="room-is-check-in">What should happen when an employee opens this door?</label>
          <select id="room-is-check-in" value={form.is_check_in_door ? "check_in" : "access_only"}
            onChange={(event) => setForm((current) => ({ ...current, is_check_in_door: event.target.value === "check_in" }))}>
            <option value="access_only">Open the door only, do not check in</option>
            <option value="check_in">Open the door and check the employee in</option>
          </select>
        </div>
      </div>
      <p className="field-hint">Only one room can be the official check-in door. Choosing check-in here replaces the current one after confirmation.</p>
      <div className="form-actions">
        <button className="button button-coral" type="submit">{busy ? "Saving…" : room ? "Save room" : "Add room"}</button>
        <button className="button button-outline" type="button" onClick={onClose}>Cancel</button>
      </div>
    </fieldset></form>
    {confirmation}
  </ModalDialog>;
}

function PermissionsDialog({ token, room, employees, onClose, onChanged }) {
  const [grants, setGrants] = useState(null);
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const [confirm, confirmation] = useConfirm();

  useEffect(() => {
    let cancelled = false;
    fetchAccessRecords(token, "grants", { room: room.id })
      .then((rows) => { if (!cancelled) setGrants(rows); })
      .catch((err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [token, room.id, version]);

  const granted = new Set((grants || []).map((row) => row.employee));
  const candidates = employees.filter((person) => person.is_active && person.account_status !== "none" && !granted.has(person.id));

  async function grant(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const saved = await grantRoomAccess(token, room.id, email.trim());
      setNotice(`${saved.employee_name} can now unlock ${room.name}.`);
      setEmail("");
      setVersion((value) => value + 1);
      onChanged();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  async function revoke(row) {
    if (!await confirm({ title: "Revoke access?", message: `${row.employee_name} will no longer be able to unlock ${room.name}.`, confirmLabel: "Revoke access" })) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await revokeRoomAccess(token, row.id);
      setNotice(`Access to ${room.name} revoked for ${row.employee_name}.`);
      setVersion((value) => value + 1);
      onChanged();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  return <ModalDialog title={`Manage permissions: ${room.name}`} wide onClose={onClose}>
    <section className="record-form">
      <Messages error={error} notice={notice} />
      <form className="access-grant-form" onSubmit={grant}><fieldset disabled={busy}>
        <label htmlFor="room-grant-email">Employee email address</label>
        <div className="access-grant-row">
          <input id="room-grant-email" type="email" list="room-grant-emails" required value={email} autoComplete="off"
            placeholder="Search or enter an employee's email" onChange={(event) => setEmail(event.target.value)} />
          <datalist id="room-grant-emails">{candidates.map((person) => <option key={person.id} value={person.email}>{person.first_name} {person.last_name}</option>)}</datalist>
          <button className="button button-coral" type="submit">Grant access</button>
        </div>
        <small className="field-hint">Only active employees of your business with a sign-in account can be granted access.</small>
      </fieldset></form>
      {grants === null ? <p className="empty-state" role="status">Loading permissions…</p>
        : <Table rows={grants} empty="Nobody has been granted this room yet." columns={[
          { title: "Employee", render: (row) => <Person name={row.employee_name} email={row.employee_email} /> },
          { title: "Granted", render: (row) => <span>{dateTime(row.granted_at)}{row.granted_by && <small className="muted"> by {row.granted_by}</small>}</span> },
        ]} actions={(row) => <button type="button" disabled={busy} onClick={() => revoke(row)}>Revoke</button>} />}
    </section>
    {confirmation}
  </ModalDialog>;
}

function RoomsPage({ token, role, business, employees, onAuthError }) {
  const rooms = useAccessRecords(token, role, "rooms", business, onAuthError);
  const [selectedId, setSelectedId] = useState(null);
  const [building, setBuilding] = useState("");
  const [floor, setFloor] = useState("");
  const [editing, setEditing] = useState(null);
  const [managing, setManaging] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, confirmation] = useConfirm();
  const employer = role === "employer";
  const admin = role === "admin";
  const { reload } = rooms;

  useEffect(() => {
    const timer = window.setInterval(reload, 10000);
    return () => window.clearInterval(timer);
  }, [reload]);

  const buildings = unique(rooms.rows.map((room) => room.building));
  const floors = unique(rooms.rows.filter((room) => !building || room.building === building).map((room) => room.floor));
  const visible = rooms.rows.filter((room) => (!building || room.building === building) && (!floor || room.floor === floor));
  const groups = Object.entries(visible.reduce((all, room) => {
    const key = `${admin ? `${room.business_name} · ` : ""}${room.building} · ${floorName(room.floor)}`;
    (all[key] ||= []).push(room);
    return all;
  }, {}));
  const selected = rooms.rows.find((room) => room.id === selectedId) || null;

  function attendanceAction(room, action) {
    return unlock(room, action);
  }

  async function unlock(room, attendanceAction = "") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await unlockRoom(token, room.id, {
        access_method: "app",
        ...(attendanceAction ? { attendance_action: attendanceAction } : {}),
      });
      setNotice(result.detail);
      await rooms.reload();
    } catch (err) {
      setError(err.message);
      if (err.status === 401) onAuthError?.(err);
    } finally { setBusy(false); }
  }

  async function remove(room) {
    if (!await confirm({ title: "Delete room?", message: `Delete ${room.name}? Everyone's access to it is revoked. Its access history is kept.`, confirmLabel: "Delete room" })) return;
    setBusy(true);
    setError("");
    try {
      await deleteRoom(token, room.id);
      setSelectedId(null);
      setNotice(`${room.name} deleted.`);
      rooms.reload();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  const detail = selected && <div className="room-detail" aria-live="polite">
    <div className="room-detail-name"><DoorIcon /><div><strong>{selected.name}</strong><span className="muted">{selected.building}, {floorName(selected.floor)}</span></div></div>
    <dl>
      {admin && <div><dt>Company</dt><dd>{selected.business_name}</dd></div>}
      {!admin && !employer && <div><dt>Your access</dt><dd>{selected.can_unlock ? "Granted" : "Not granted"}</dd></div>}
      {(employer || admin) && <div><dt>Door</dt><dd>{selected.door_identifier}</dd></div>}
      <div><dt>Attendance</dt><dd>{selected.is_check_in_door ? "Official check-in door" : "Access only"}</dd></div>
      {(employer || admin) && <div><dt>Authorized users</dt><dd>{selected.authorized_users} {selected.authorized_users === 1 ? "employee" : "employees"}</dd></div>}
      <div><dt>Door hardware</dt><dd>{DEVICE_STATUS[selected.device_status] || selected.device_status}</dd></div>
    </dl>
    <div className="room-detail-actions">
      {selected.can_unlock && selected.is_check_in_door && <div className="attendance-scan-actions">
        <strong>{selected.attendance_state === "inside" ? "You are currently in the office"
          : selected.attendance_state === "outside" ? "You are currently outside the office"
          : selected.attendance_state === "completed" ? "Your workday is complete"
          : "Start your workday"}</strong>
        {selected.attendance_state === "not_started" && <button type="button" className="button button-coral" disabled={busy}
          onClick={() => attendanceAction(selected, "scan_in")}>Check In, first arrival</button>}
        {selected.attendance_state === "inside" && <>
          <button type="button" className="button button-coral" disabled={busy}
            onClick={() => attendanceAction(selected, "scan_out")}>Scan Out, leaving temporarily</button>
          <button type="button" className="button button-outline" disabled={busy}
            onClick={() => attendanceAction(selected, "check_out")}>Check Out, final departure</button>
        </>}
        {selected.attendance_state === "outside" && <button type="button" className="button button-coral" disabled={busy}
          onClick={() => attendanceAction(selected, "scan_in")}>Scan In, returning</button>}
        {selected.device_status !== "online" && <small className="muted">The physical door is offline. Leaving is still recorded; arriving needs the ESP32 online.</small>}
      </div>}
      {(employer || selected.can_unlock) && !(selected.can_unlock && selected.is_check_in_door) && <button type="button" className="button button-coral"
        disabled={busy || selected.device_status !== "online"} onClick={() => unlock(selected)}>{busy ? "Sending…" : "Unlock physical door"}</button>}
      {employer && <>
        <button type="button" className="button button-outline" onClick={() => setManaging(selected)}>Manage permissions</button>
        <button type="button" className="button button-outline" onClick={() => setEditing(selected)}>Edit</button>
        <button type="button" className="danger-link" disabled={busy} onClick={() => remove(selected)}>Delete</button>
      </>}
      {role === "employee" && !selected.can_unlock && <p className="muted">Your employer has not granted you access to this room.</p>}
      {admin && <p className="muted">Administrators oversee rooms but cannot unlock doors.</p>}
    </div>
  </div>;

  return <>
    <Heading title={role === "employee" ? "My Rooms" : "Rooms & Doors"}
      description={role === "employee" ? "Select a room to unlock it when you are at the door." : "Select a room to view its details and unlock its door."}
      action={employer && <button type="button" className="button button-coral" onClick={() => setEditing({})}>+ Add room</button>} />
    <Messages error={error || rooms.error} notice={notice} />
    {rooms.rows.length > 0 && <div className="access-filters">
      <select aria-label="Building" value={building} onChange={(event) => { setBuilding(event.target.value); setFloor(""); }}>
        <option value="">All buildings</option>{buildings.map((value) => <option key={value} value={value}>{value}</option>)}
      </select>
      <select aria-label="Floor" value={floor} onChange={(event) => setFloor(event.target.value)}>
        <option value="">All floors</option>{floors.map((value) => <option key={value} value={value}>{floorName(value)}</option>)}
      </select>
    </div>}
    {rooms.loading ? <p className="empty-state" role="status">Loading rooms…</p>
      : !rooms.rows.length ? <section className="panel floor-plan"><p className="empty-state">{employer ? "No rooms yet. Add the rooms with controlled doors to start granting access." : "No rooms have been added yet."}</p></section>
      : groups.map(([title, list]) => <section key={title} className="panel floor-plan" aria-label={title}>
        <h3>{title}</h3>
        <p className="muted">{list.length} {list.length === 1 ? "room" : "rooms"}</p>
        <div className="room-grid">{list.map((room) => <button key={room.id} type="button" aria-pressed={room.id === selectedId}
          className={`room-tile${room.id === selectedId ? " selected" : ""}${room.is_check_in_door ? " check-in" : ""}${role === "employee" && !room.can_unlock ? " locked" : ""}`}
          onClick={() => { setSelectedId(room.id === selectedId ? null : room.id); setError(""); setNotice(""); }}>
          <DoorIcon />
          <span>{room.name}{room.is_check_in_door && <small className="check-in-label">Check-in door</small>}{role === "employee" && <small>{room.can_unlock ? "Access granted" : "No access"}</small>}</span>
        </button>)}</div>
        {selected && list.includes(selected) && detail}
      </section>)}
    {editing && <RoomForm token={token} room={editing.id ? editing : null}
      currentCheckInDoor={rooms.rows.find((room) => room.is_check_in_door) || null}
      onClose={() => setEditing(null)} onSaved={(saved) => {
      setEditing(null);
      setSelectedId(saved.id);
      setNotice(`${saved.name} saved.`);
      rooms.reload();
    }} />}
    {managing && <PermissionsDialog token={token} room={managing} employees={employees} onClose={() => setManaging(null)} onChanged={rooms.reload} />}
    {confirmation}
  </>;
}

// --- Access Permissions -----------------------------------------------------------

function Checklist({ id, title, items, selected, onChange, empty }) {
  const [search, setSearch] = useState("");
  const term = search.trim().toLowerCase();
  const shown = items.filter((item) => `${item.label} ${item.detail}`.toLowerCase().includes(term));
  const allShown = shown.length > 0 && shown.every((item) => selected.has(item.id));
  const update = (ids, on) => {
    const next = new Set(selected);
    ids.forEach((value) => (on ? next.add(value) : next.delete(value)));
    onChange(next);
  };
  return <fieldset className="access-pick">
    <legend>{title} <small>{selected.size} selected</small></legend>
    {items.length ? <>
      <input type="search" aria-label={`Search ${title.toLowerCase()}`} placeholder={`Search ${title.toLowerCase()}…`} value={search} onChange={(event) => setSearch(event.target.value)} />
      <label className="access-pick-all"><input type="checkbox" checked={allShown} disabled={!shown.length}
        onChange={(event) => update(shown.map((item) => item.id), event.target.checked)} /> Select all{term ? " shown" : ""}</label>
      <div className="access-pick-list" id={id}>
        {shown.map((item) => <label key={item.id}>
          <input type="checkbox" checked={selected.has(item.id)} onChange={(event) => update([item.id], event.target.checked)} />
          <span><strong>{item.label}</strong><small>{item.detail}</small></span>
        </label>)}
        {!shown.length && <p className="muted">Nothing matches this search.</p>}
      </div>
    </> : <p className="muted">{empty}</p>}
  </fieldset>;
}

function GrantAccessDialog({ token, employees, rooms, onClose, onGranted }) {
  const [people, setPeople] = useState(() => new Set());
  const [chosenRooms, setChosenRooms] = useState(() => new Set());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const eligible = employees.filter((person) => person.is_active && person.account_status !== "none");

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try { onGranted(await grantRoomAccessBulk(token, [...people], [...chosenRooms])); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  return <ModalDialog title="Give access" wide onClose={onClose}>
    <form className="record-form" onSubmit={submit}><fieldset disabled={busy}>
      {error && <p className="message error" role="alert">{error}</p>}
      <p className="muted">Tick one or more employees and one or more rooms. Each employee gets access to every room you tick.</p>
      <div className="access-pick-columns">
        <Checklist id="grant-people" title="Employees" selected={people} onChange={setPeople}
          empty="No active employees with a sign-in account yet."
          items={eligible.map((person) => ({ id: person.id, label: `${person.first_name} ${person.last_name}`, detail: person.email }))} />
        <Checklist id="grant-rooms" title="Rooms" selected={chosenRooms} onChange={setChosenRooms}
          empty="No rooms yet. Add rooms on Rooms & Doors first."
          items={rooms.map((room) => ({ id: room.id, label: room.name, detail: `${room.building}, ${floorName(room.floor)}` }))} />
      </div>
      <div className="form-actions">
        <button className="button button-coral" type="submit" disabled={!people.size || !chosenRooms.size}>
          {busy ? "Granting…" : `Give access (${people.size} ${people.size === 1 ? "employee" : "employees"} × ${chosenRooms.size} ${chosenRooms.size === 1 ? "room" : "rooms"})`}
        </button>
        <button className="button button-outline" type="button" onClick={onClose}>Cancel</button>
      </div>
    </fieldset></form>
  </ModalDialog>;
}

// Every room one employee may unlock, opened from the Access Permissions list.
function EmployeeAccessDialog({ person, employer, onRevoke, onClose }) {
  return <ModalDialog title={person.name} onClose={onClose} wide>
    <section className="records-panel" aria-label={`Rooms ${person.name} can unlock`}>
      <p className="muted">{person.email} · {person.rooms.length} {person.rooms.length === 1 ? "room" : "rooms"}</p>
      <Table rows={person.rooms} empty="No rooms." columns={[
        { title: "Room", render: (row) => <span>{row.room_name}<small className="muted"> {row.building}, {floorName(row.floor)}</small></span> },
        { title: "Granted", render: (row) => <span>{dateTime(row.granted_at)}{row.granted_by && <small className="muted"> by {row.granted_by}</small>}</span> },
      ]} actions={employer ? (row) => <button type="button" onClick={() => onRevoke(row)}>Revoke</button> : undefined} />
    </section>
    <div className="form-actions">
      <button type="button" className="button button-outline" onClick={onClose}>Close</button>
    </div>
  </ModalDialog>;
}

function PermissionsPage({ token, role, business, employees, onAuthError }) {
  const grants = useAccessRecords(token, role, "grants", business, onAuthError);
  const changes = useAccessRecords(token, role, "changes", business, onAuthError);
  const rooms = useAccessRecords(token, role, "rooms", business, onAuthError);
  const [giving, setGiving] = useState(false);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [viewingId, setViewingId] = useState(null);
  const [confirm, confirmation] = useConfirm();
  const employer = role === "employer";
  const term = search.trim().toLowerCase();
  const matching = grants.rows.filter((row) => [row.employee_name, row.employee_email, row.room_name, row.building].join(" ").toLowerCase().includes(term));
  // One row per person; their rooms live in the details popup.
  const people = Object.values(matching.reduce((all, row) => {
    (all[row.employee] ||= { id: row.employee, name: row.employee_name, email: row.employee_email, rooms: [] }).rooms.push(row);
    return all;
  }, {}));
  // Read back from the grouped list, so a revoke inside the popup updates it.
  const viewing = people.find((person) => person.id === viewingId) || null;

  async function revoke(row) {
    if (!await confirm({ title: "Revoke access?", message: `${row.employee_name} will no longer be able to unlock ${row.room_name}.`, confirmLabel: "Revoke access" })) return;
    setError("");
    try {
      await revokeRoomAccess(token, row.id);
      setNotice(`Access to ${row.room_name} revoked for ${row.employee_name}.`);
      grants.reload();
      changes.reload();
    } catch (err) { setError(err.message); }
  }

  return <>
    <Heading title="Access Permissions" description="Who can unlock which room."
      action={employer && <button type="button" className="button button-coral" onClick={() => { setNotice(""); setGiving(true); }}>+ Give access</button>} />
    <Messages error={error || grants.error || changes.error} notice={notice} />
    <section className="panel records-panel" aria-label="Room permissions">
      <div className="records-toolbar"><span className="record-count">{people.length} {people.length === 1 ? "employee" : "employees"}</span>
        <div className="records-filters"><input type="search" aria-label="Search permissions" placeholder="Search people or rooms…" value={search} onChange={(event) => setSearch(event.target.value)} /></div></div>
      {grants.loading ? <p className="empty-state" role="status">Loading permissions…</p> : <Table rows={people} empty={grants.rows.length ? "No permissions match this search." : employer ? "No room access has been granted yet. Use Give access to choose employees and rooms." : "No room access has been granted yet."} columns={[
        { title: "Employee", render: (row) => <Person name={row.name} email={row.email} /> },
        { title: "Rooms", render: (row) => <span>{row.rooms.length} {row.rooms.length === 1 ? "room" : "rooms"}<small className="muted"> {row.rooms.map((grant) => grant.room_name).join(", ")}</small></span> },
      ]} actions={(row) => <button type="button" onClick={() => setViewingId(row.id)}>View details</button>} />}
      <details className="decided-requests access-changes">
        <summary>Permission changes ({changes.rows.length})</summary>
        <Table rows={changes.rows} empty="No permission changes yet." columns={[
          { title: "When", render: (row) => dateTime(row.created_at) },
          { title: "Change", render: (row) => <span className={`status-badge status-${row.change}`}>{row.change_label}</span> },
          { title: "Employee", render: (row) => <Person name={row.employee_name} email={row.employee_email} /> },
          { title: "Room", render: (row) => row.room_name },
          { title: "By", render: (row) => <span>{row.changed_by}{row.note && <small className="muted"> {row.note}</small>}</span> },
        ]} />
      </details>
    </section>
    {viewing && <EmployeeAccessDialog person={viewing} employer={employer} onRevoke={revoke} onClose={() => setViewingId(null)} />}
    {giving && <GrantAccessDialog token={token} employees={employees} rooms={rooms.rows} onClose={() => setGiving(false)} onGranted={(result) => {
      setGiving(false);
      setNotice(`Access given: ${result.granted} new ${result.granted === 1 ? "permission" : "permissions"}${result.already_had_access ? `, ${result.already_had_access} already had access` : ""}.`);
      grants.reload();
      changes.reload();
    }} />}
    {confirmation}
  </>;
}

// --- Access History ------------------------------------------------------------------

function HistoryPage({ token, role, business, onAuthError }) {
  const history = useAccessRecords(token, role, "history", business, onAuthError);
  const [result, setResult] = useState("");
  const [search, setSearch] = useState("");
  const term = search.trim().toLowerCase();
  const visible = history.rows.filter((row) => (!result || row.result === result)
    && [row.user_name, row.user_email, row.room_name, row.building, row.business_name].join(" ").toLowerCase().includes(term));
  const own = role === "employee";

  return <>
    <Heading title="Access History" description={own ? "Every time you asked to unlock a door, and what happened." : "Every request to unlock a door, granted or denied."} />
    <Messages error={history.error} />
    <section className="panel records-panel" aria-label="Access history">
      <div className="records-toolbar"><span className="record-count">{visible.length} {visible.length === 1 ? "attempt" : "attempts"}</span><div className="records-filters">
        <input type="search" aria-label="Search access history" placeholder={own ? "Search rooms…" : "Search people or rooms…"} value={search} onChange={(event) => setSearch(event.target.value)} />
        <select aria-label="Filter by result" value={result} onChange={(event) => setResult(event.target.value)}>
          <option value="">All results</option><option value="granted">Granted</option><option value="denied">Denied</option>
        </select>
      </div></div>
      {history.loading ? <p className="empty-state" role="status">Loading access history…</p> : <Table rows={visible} empty={history.rows.length ? "No attempts match these filters." : "No unlock attempts recorded yet."} columns={[
        { title: "Date and time", render: (row) => dateTime(row.created_at) },
        ...(own ? [] : [{ title: "Person", render: (row) => <Person name={row.user_name} email={row.user_email} /> }]),
        ...(role === "admin" ? [{ title: "Company", render: (row) => row.business_name }] : []),
        { title: "Room", render: (row) => <span>{row.room_name}{row.building && <small className="muted"> {row.building}, {floorName(row.floor)}</small>}</span> },
        { title: "Method", render: (row) => row.access_method_label },
        { title: "Result", render: (row) => <span className={`status-badge status-${row.result}`}>{row.result === "granted" ? "Granted" : "Denied"}</span> },
        { title: "Details", render: (row) => row.denial_reason_label || row.unlock_status_label || "—" },
      ]} />}
    </section>
  </>;
}

// --- Layout --------------------------------------------------------------------------------

export default function AccessControl({ token, role, employees = [], onAuthError }) {
  const { pathname } = useLocation();
  const [business, setBusiness] = useState("");
  const [businesses, setBusinesses] = useState([]);
  const sections = role === "employee" ? ["rooms", "history"]
    : ["rooms", "permissions", "history"];
  const current = sections.find((key) => pathname.startsWith(`${BASE}/${key}`)) || "rooms";

  useEffect(() => {
    if (role !== "admin") return undefined;
    let cancelled = false;
    fetchAdminBusinesses(token).then((rows) => { if (!cancelled) setBusinesses(rows); }).catch(() => {});
    return () => { cancelled = true; };
  }, [role, token]);

  const props = { token, role, business, onAuthError };
  return <div className="access-layout">
    <nav className="access-sidebar" aria-label="Access control">
      <strong>Access Control</strong>
      {sections.map((key) => <Link key={key} to={key === "rooms" ? BASE : `${BASE}/${key}`} className={current === key ? "selected" : undefined}
        aria-current={current === key ? "page" : undefined}>{SECTION_TITLES[key]}</Link>)}
    </nav>
    <div className="access-content">
      <p className="access-breadcrumb">Access Control <span aria-hidden="true">›</span> {SECTION_TITLES[current]}</p>
      {role === "admin" && <div className="access-filters">
        <select aria-label="Company" value={business} onChange={(event) => setBusiness(event.target.value)}>
          <option value="">All companies</option>{businesses.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
        </select>
      </div>}
      {current === "rooms" && <RoomsPage key={business} {...props} employees={employees} />}
      {current === "permissions" && <PermissionsPage {...props} employees={employees} />}
      {current === "history" && <HistoryPage {...props} />}
    </div>
  </div>;
}
