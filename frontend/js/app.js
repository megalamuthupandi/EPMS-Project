/* EPMS Frontend - API-connected application */
(() => {
  "use strict";

  const API_BASE = "http://127.0.0.1:8000";
  const API_PREFIX = "/api/v1";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const state = {
    token: localStorage.getItem("epms_access_token") || "",
    user: null,
    roleName: "Member",
    currentPage: "dashboard",
    cache: {},
    modal: null
  };

  const PAGE = {
    dashboard: ["Overview", "YOUR WORKSPACE", "Here’s what’s happening across your workspace."],
    projects: ["Projects", "WORK MANAGEMENT", "Plan and track your projects."],
    tasks: ["Tasks", "WORK MANAGEMENT", "Manage tasks, priorities and deadlines."],
    completed_work: ["Completed Work", "WORK MANAGEMENT", "Review completed tasks and projects."],
    milestones: ["Milestones", "WORK MANAGEMENT", "Track important project checkpoints."],
    members: ["Project members", "TEAM", "Manage project membership."],
    chat: ["Team Group Chat", "COLLABORATION", "Communicate with your project team."],
    task_chat: ["Task Conversations", "COLLABORATION", "Task group conversation for the project PM, Team Lead and assigned employee."],
    comments: ["Comments", "COLLABORATION", "Follow project conversations."],
    notifications: ["Notifications", "COLLABORATION", "Stay up to date."],
    users: ["User management", "ADMINISTRATION", "Manage workspace accounts."],
    roles: ["Roles & permissions", "ADMINISTRATION", "Review roles and permission assignments."],
    audit_logs: ["Audit logs", "ADMINISTRATION", "Review recorded system activity."]
  };

  const RESOURCE = {
    projects: { endpoint: "projects", title: "Projects", fields: [
      ["name","Project name","text",true],["description","Description","textarea"],
      ["owner_id","Owner user ID","number",true],["start_date","Start date","date"],
      ["due_date","Due date","date"],["status","Status","select",true,["PLANNING","ACTIVE","ON_HOLD","COMPLETED","CANCELLED"]]
    ], columns:["id","name","owner_id","status","start_date","due_date"] },
    tasks: { endpoint:"tasks", title:"Tasks", fields:[
      ["project_id","Project","number",true],["assignee_id","Assign Employee","number"],
      ["title","Task title","text",true],["description","Description","textarea"],
      ["status","Status","select",true,["TODO","IN_PROGRESS","IN_REVIEW","DONE","BLOCKED"]],
      ["priority","Priority","select",true,["LOW","MEDIUM","HIGH","URGENT"]],["due_date","Due date","date"]
    ], columns:["id","title","project_id","assignee_id","status","priority","due_date"] },
    milestones:{endpoint:"milestones",title:"Milestones",fields:[
      ["project_id","Project ID","number",true],["title","Title","text",true],
      ["due_date","Due date","date"],["is_completed","Completed","checkbox"]
    ],columns:["id","project_id","title","due_date","is_completed"]},
    members:{endpoint:"project_members",title:"Project members",fields:[
      ["project_id","Project ID","number",true],["user_id","User ID","number",true],
      ["project_role","Project role","select",true,["MANAGER","LEAD","MEMBER"]]
    ],columns:["id","project_id","user_id","project_role","joined_at"]},
    comments:{endpoint:"comments",title:"Comments",fields:[
      ["task_id","Task ID","number",true],["user_id","User ID","number",true],
      ["body","Comment","textarea",true]
    ],columns:["id","task_id","user_id","body","created_at"]},
    notifications:{endpoint:"notifications",title:"Notifications",fields:[
      ["user_id","User ID","number",true],["title","Title","text",true],
      ["message","Message","textarea",true],["is_read","Read","checkbox"]
    ],columns:["id","user_id","title","message","is_read","created_at"]},
    audit_logs:{endpoint:"audit_logs",title:"Audit logs",fields:[
      ["user_id","User ID","number"],["action","Action","text",true],
      ["entity_type","Entity type","text",true],["entity_id","Entity ID","number"],
      ["details","Details","textarea"]
    ],columns:["id","user_id","action","entity_type","entity_id","details","created_at"]}
  };

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, ch => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    }[ch]));
  }
  function toast(message, type = "success") {
    const region = $("#toast-region");
    if (!region) return;
    const node = document.createElement("div");
    node.className = `toast ${type === "error" ? "toast-error" : ""}`;
    node.textContent = message;
    region.appendChild(node);
    setTimeout(() => node.remove(), 4200);
  }
  function errorMessage(data, fallback = "Something went wrong.") {
    if (!data) return fallback;
    if (typeof data.detail === "string") return data.detail;
    if (data.detail) return JSON.stringify(data.detail);
    return data.message || fallback;
  }
  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
    if (state.token && !options.public) headers.Authorization = `Bearer ${state.token}`;
    const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
    const raw = await response.text();
    let data = null;
    try { data = raw ? JSON.parse(raw) : null; } catch { data = raw; }
    if (!response.ok) {
      if (response.status === 401 && !options.noLogout && state.token) signOut(false);
      throw new Error(errorMessage(data, `${response.status} ${response.statusText}`));
    }
    return data;
  }
  function setToken(token) {
    state.token = token || "";
    if (state.token) localStorage.setItem("epms_access_token", state.token);
    else localStorage.removeItem("epms_access_token");
  }
  function showLogin() {
    $("#login-view")?.classList.remove("hidden");
    $("#app-view")?.classList.add("hidden");
  }
  function showApp() {
    $("#login-view")?.classList.add("hidden");
    $("#app-view")?.classList.remove("hidden");
    $("#header-name").textContent = state.user?.full_name || "User";
    $("#user-avatar").textContent = (state.user?.full_name || "U").trim().charAt(0).toUpperCase();
    const roleKey = String(state.roleName || "Member").trim().toUpperCase();
    const displayRole = roleKey.replace(/_/g, " ");
    const userId = state.user?.id;
    const roleIdLabel = ({ADMIN:"ADMIN", PROJECT_MANAGER:"PM", TEAM_LEAD:"TL", EMPLOYEE:"EMPLOYEE"})[roleKey] || displayRole;
    const roleSerialId = state.user?.role_serial_id;
    $("#header-role").textContent = userId != null
      ? `${displayRole} · EMP ID: ${userId}${roleSerialId != null ? `\n${roleIdLabel} ID: ${roleSerialId}` : ""}`
      : displayRole;
    const isAdmin = state.roleName.toUpperCase() === "ADMIN";
    $$(".admin-nav").forEach(el => el.classList.toggle("hidden", !isAdmin));
  }
  async function loadProfile() {
    state.user = await api(`${API_PREFIX}/auth/me`);
    try {
      const roles = await api(`${API_PREFIX}/roles?limit=200`);
      state.roleName = roles.find(r => r.id === state.user.role_id)?.name || `Role ${state.user.role_id}`;
    } catch {
      state.roleName = `Role ${state.user.role_id}`;
    }
    showApp();
    await navigate("dashboard");
  }
  async function login(email, password) {
    const result = await api(`${API_PREFIX}/auth/login`, {
      method:"POST", public:true, noLogout:true,
      body:JSON.stringify({email,password,company_code:$("#login-company-code").value.trim()})
    });
    setToken(result.access_token);
    await loadProfile();
    toast("Signed in successfully.");
  }
  function signOut(showMessage = true) {
    setToken("");
    state.user = null;
    state.cache = {};
    showLogin();
    if (showMessage) toast("You have signed out.");
  }

  function closeModal() {
    $("#modal-root").innerHTML = "";
    state.modal = null;
  }
  function openModal(content) {
    $("#modal-root").innerHTML = `<div class="modal-backdrop" id="modal-backdrop"><div class="modal">${content}</div></div>`;
    state.modal = $("#modal-backdrop");
    $("#modal-backdrop").addEventListener("click", e => {
      if (e.target.id === "modal-backdrop") closeModal();
    });
    $$("[data-close-modal]").forEach(btn => btn.addEventListener("click", closeModal));
  }

  function openSignup() {
    openModal(`
      <div class="modal-head"><h3>Create an account</h3><button class="modal-close" data-close-modal>×</button></div>
      <p class="muted">New accounts are created with the EMPLOYEE role.</p>
      <form id="signup-form" class="stack-form">
        <label class="field">Company ID<input name="company_code" placeholder="ABC12345" required></label>
        <label class="field">Full name<input name="full_name" minlength="2" maxlength="120" required></label>
        <label class="field">Email<input name="email" type="email" required></label>
        <label class="field">Password<input name="password" type="password" minlength="8" maxlength="128" required></label>
        <label class="field">Confirm password<input name="confirm" type="password" minlength="8" required></label>
        <div id="signup-error" class="form-error"></div>
        <div class="modal-actions"><button type="button" class="btn btn-secondary" data-close-modal>Cancel</button><button class="btn btn-primary" type="submit">Create account</button></div>
      </form>`);
    $("#signup-form").addEventListener("submit", async e => {
      e.preventDefault();
      const f = e.currentTarget, err = $("#signup-error");
      if (f.password.value !== f.confirm.value) { err.textContent = "Passwords do not match."; return; }
      try {
        await api(`${API_PREFIX}/auth/register`, {method:"POST",public:true,noLogout:true,
          body:JSON.stringify({company_code:f.company_code.value.trim(),full_name:f.full_name.value.trim(),email:f.email.value.trim(),password:f.password.value})});
        closeModal(); $("#login-email").value = f.email.value.trim();
        toast("Account created. Please sign in.");
      } catch (ex) { err.textContent = ex.message; }
    });
  }

  function openCompanySignup() {
    openModal(`
      <div class="modal-head"><h3>Register a company</h3><button class="modal-close" data-close-modal>×</button></div>
      <p class="muted">Create a company workspace and its first Admin account.</p>
      <form id="company-signup-form" class="stack-form">
        <label class="field">Company name<input name="company_name" minlength="2" maxlength="160" required></label>
        <label class="field">Company ID<input name="company_code" placeholder="ABC12345" pattern="[A-Za-z0-9]{3,40}" required></label>
        <label class="field">Admin full name<input name="admin_full_name" minlength="2" required></label>
        <label class="field">Admin email<input name="admin_email" type="email" required></label>
        <label class="field">Admin password<input name="admin_password" type="password" minlength="8" required></label>
        <div id="company-signup-error" class="form-error"></div>
        <div class="modal-actions"><button type="button" class="btn btn-secondary" data-close-modal>Cancel</button><button class="btn btn-primary">Create company</button></div>
      </form>`);
    $("#company-signup-form").onsubmit=async e=>{e.preventDefault();const f=e.currentTarget;try{const result=await api(`${API_PREFIX}/companies/register`,{method:"POST",public:true,noLogout:true,body:JSON.stringify({company_name:f.company_name.value.trim(),company_code:f.company_code.value.trim(),admin_full_name:f.admin_full_name.value.trim(),admin_email:f.admin_email.value.trim(),admin_password:f.admin_password.value})});closeModal();$("#login-company-code").value=result.company_code;$("#login-email").value=f.admin_email.value.trim();toast(`Company created. Admin ID: ${result.admin_employee_code}`);}catch(ex){$("#company-signup-error").textContent=ex.message;}};
  }

  function openForgotPassword() {
    openModal(`
      <div class="modal-head"><h3>Forgot password</h3><button class="modal-close" data-close-modal>×</button></div>
      <p class="muted">Enter your registered email. Development mode may show a reset token here.</p>
      <form id="forgot-form" class="stack-form">
        <label class="field">Email<input name="email" type="email" value="${esc($("#login-email").value)}" required></label>
        <div id="forgot-result" class="form-error"></div>
        <div class="modal-actions"><button type="button" class="btn btn-secondary" data-close-modal>Cancel</button><button class="btn btn-primary">Continue</button></div>
      </form>`);
    $("#forgot-form").addEventListener("submit", async e => {
      e.preventDefault();
      const email = e.currentTarget.email.value.trim(), out = $("#forgot-result");
      out.textContent = "Requesting reset token…";
      try {
        const data = await api(`${API_PREFIX}/auth/forgot-password`, {method:"POST",public:true,noLogout:true,body:JSON.stringify({email})});
        if (!data.reset_token) {
          out.textContent = `${data.message || "Reset request received."} If this is your development environment, set RESET_TOKEN_EXPOSE=true in .env and restart the API.`;
          return;
        }
        openResetPassword(email, data.reset_token, data.expires_in_minutes);
      } catch (ex) { out.textContent = ex.message; }
    });
  }
  function openResetPassword(email, token = "") {
    openModal(`
      <div class="modal-head"><h3>Reset password</h3><button class="modal-close" data-close-modal>×</button></div>
      <form id="reset-form" class="stack-form">
        <label class="field">Reset token<textarea name="token" rows="3" required>${esc(token)}</textarea></label>
        <label class="field">New password<input name="new_password" type="password" minlength="8" maxlength="128" required></label>
        <label class="field">Confirm password<input name="confirm" type="password" minlength="8" required></label>
        <div id="reset-error" class="form-error"></div>
        <div class="modal-actions"><button type="button" class="btn btn-secondary" data-close-modal>Cancel</button><button class="btn btn-primary">Reset password</button></div>
      </form>`);
    $("#reset-form").addEventListener("submit", async e => {
      e.preventDefault();
      const f=e.currentTarget, out=$("#reset-error");
      if(f.new_password.value!==f.confirm.value){out.textContent="Passwords do not match.";return;}
      try {
        const data=await api(`${API_PREFIX}/auth/reset-password`,{method:"POST",public:true,noLogout:true,body:JSON.stringify({token:f.token.value.trim(),new_password:f.new_password.value})});
        closeModal(); $("#login-email").value=email||""; $("#login-password").value="";
        toast(data.message || "Password reset. Please sign in.");
      } catch(ex){out.textContent=ex.message;}
    });
  }

  function formatValue(v) {
    if (v === null || v === undefined || v === "") return "—";
    if (typeof v === "boolean") return v ? "Yes" : "No";
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  }
  function renderTable(rows, columns, actions = true) {
    if (!rows.length) return `<div class="empty-state"><h3>No records found</h3><p>There are no records to display yet.</p></div>`;
    const policy = typeof actions === "function" ? actions : (typeof actions === "object" ? actions : (actions ? {view:true,edit:true,delete:true} : null));
    return `<div class="table-wrap"><table class="data-table"><thead><tr>${columns.map(c=>`<th>${esc(c.replaceAll("_"," "))}</th>`).join("")}${policy?"<th>Actions</th>":""}</tr></thead><tbody>
      ${rows.map(row=>{const rowPolicy=typeof policy==="function"?policy(row):policy;return `<tr>${columns.map(c=>`<td>${esc(formatValue(row[c]))}</td>`).join("")}${rowPolicy?`<td class="row-actions">${rowPolicy.view?`<button class="btn btn-secondary btn-sm" data-view="${row.id}">View</button>`:""}${rowPolicy.edit?`<button class="btn btn-secondary btn-sm" data-edit="${row.id}">Edit</button>`:""}${rowPolicy.delete?`<button class="btn btn-danger btn-sm" data-delete="${row.id}">Delete</button>`:""}</td>`:""}</tr>`;}).join("")}
    </tbody></table></div>`;
  }
  function actionPolicy(page) {
    const role = (state.roleName || "").toUpperCase();
    if (role === "TEAM_LEAD" && page === "projects") return {view:true, edit:false, delete:false};
    if (role === "PROJECT_MANAGER" && page === "projects") return row => ({view:true, edit:Number(row.owner_id)===Number(state.user?.id), delete:Number(row.owner_id)===Number(state.user?.id)});
    if (role === "TEAM_LEAD" && page === "tasks") return {view:true, edit:true, delete:true};
    if (role === "TEAM_LEAD" && page === "milestones") return {view:true, edit:true, delete:false};
    if (page === "audit_logs") return {view:true, edit:false, delete:false};
    if (page === "notifications") return {view:true, edit:false, delete:false};
    return {view:true, edit:true, delete:true};
  }
  function openRecordView(page, record) {
    const cfg=RESOURCE[page];
    const entries=cfg.columns.filter(k=>Object.prototype.hasOwnProperty.call(record,k));
    openModal(`<div class="modal-head"><h3>View ${esc(cfg.title)} #${esc(record.id)}</h3><button class="modal-close" data-close-modal>×</button></div>
      <div class="table-wrap"><table class="data-table"><tbody>${entries.map(k=>`<tr><th>${esc(k.replaceAll("_"," "))}</th><td>${esc(formatValue(record[k]))}</td></tr>`).join("")}</tbody></table></div>
      <div class="modal-actions"><button class="btn btn-secondary" data-close-modal>Close</button></div>`);
  }
  function openMilestoneStatusForm(record) {
    openModal(`<div class="modal-head"><h3>Update milestone status #${esc(record.id)}</h3><button class="modal-close" data-close-modal>×</button></div><form id="milestone-status-form" class="stack-form"><label class="field checkbox-field"><input type="checkbox" name="is_completed" ${record.is_completed?"checked":""}> Completed</label><p class="muted">Team Leads can change only the completion status.</p><div id="milestone-status-error" class="form-error"></div><div class="modal-actions"><button type="button" class="btn btn-secondary" data-close-modal>Cancel</button><button class="btn btn-primary">Save status</button></div></form>`);
    $("#milestone-status-form").onsubmit=async e=>{e.preventDefault();try{await api(`${API_PREFIX}/milestones/${record.id}`,{method:"PATCH",body:JSON.stringify({is_completed:e.currentTarget.is_completed.checked})});closeModal();toast("Milestone status updated.");await navigate("milestones");}catch(ex){$("#milestone-status-error").textContent=ex.message;}};
  }
  function fieldControl(field, value) {
    const [key,label,type,required,options] = field;
    const req = required ? "required" : "";
    const val = value ?? "";
    if(type==="textarea") return `<label class="field">${esc(label)}<textarea name="${key}" rows="3" ${req}>${esc(val)}</textarea></label>`;
    if(type==="select") return `<label class="field">${esc(label)}<select name="${key}" ${req}>${!required?'<option value="">—</option>':""}${options.map(o=>`<option ${o===val?"selected":""}>${o}</option>`).join("")}</select></label>`;
    if(type==="checkbox") return `<label class="field checkbox-field"><input type="checkbox" name="${key}" ${val?"checked":""}> ${esc(label)}</label>`;
    return `<label class="field">${esc(label)}<input name="${key}" type="${type}" value="${esc(val)}" ${req}></label>`;
  }
  function parseForm(form, fields) {
    const result={};
    fields.forEach(([key,,type])=>{
      const el=form.elements[key]; if(!el) return;
      if(type==="checkbox") result[key]=el.checked;
      else if(type==="number") result[key]=el.value===""?null:Number(el.value);
      else result[key]=el.value===""?null:el.value;
    });
    return result;
  }
  async function openRecordForm(page, record = null) {
    const config=RESOURCE[page], editing=!!record;
    let taskProjects=[], taskAssignees=[];
    if(page==="tasks"){
      try{
        taskProjects=await api(`${API_PREFIX}/projects?limit=200`);
        if(record?.project_id) taskAssignees=await api(`${API_PREFIX}/tasks/assignees?project_id=${record.project_id}`);
      }catch(ex){toast(`Unable to load task assignment options: ${ex.message}`,"error");return;}
    }
    openModal(`
      <div class="modal-head"><h3>${editing?"Edit":"Create"} ${esc(config.title)}</h3><button class="modal-close" data-close-modal>×</button></div>
      <form id="record-form" class="stack-form">${config.fields.map(f=>{
        if(page==="tasks" && f[0]==="project_id") return `<label class="field">Project<select name="project_id" id="task-project-select" required><option value="">Select project</option>${taskProjects.map(p=>`<option value="${p.id}" ${p.id===record?.project_id?"selected":""}>${esc(p.name)} (#${p.id})</option>`).join("")}</select></label>`;
        if(page==="tasks" && f[0]==="assignee_id") return `<label class="field">Assign Employee<select name="assignee_id" id="task-assignee-select"><option value="">Unassigned</option>${taskAssignees.map(u=>`<option value="${u.id}" ${u.id===record?.assignee_id?"selected":""}>${esc(u.full_name)}</option>`).join("")}</select></label>`;
        return fieldControl(f,record?.[f[0]]);
      }).join("")}
      <div id="record-error" class="form-error"></div>
      <div class="modal-actions"><button type="button" class="btn btn-secondary" data-close-modal>Cancel</button><button class="btn btn-primary">${editing?"Save changes":"Create"}</button></div></form>`);
    if(page==="tasks"){
      $("#task-project-select").addEventListener("change",async e=>{
        const select=$("#task-assignee-select"); select.innerHTML='<option value="">Unassigned</option>';
        if(!e.target.value)return;
        try{const people=await api(`${API_PREFIX}/tasks/assignees?project_id=${e.target.value}`);select.innerHTML='<option value="">Unassigned</option>'+people.map(u=>`<option value="${u.id}">${esc(u.full_name)}</option>`).join("");}
        catch(ex){toast(ex.message,"error");}
      });
    }
    $("#record-form").addEventListener("submit",async e=>{
      e.preventDefault(); const payload=parseForm(e.currentTarget,config.fields),out=$("#record-error");
      Object.keys(payload).forEach(k=>{if(payload[k]===null) delete payload[k];});
      try{
        await api(`${API_PREFIX}/${config.endpoint}${editing?`/${record.id}`:""}`,{
          method:editing?"PATCH":"POST",body:JSON.stringify(payload)
        });
        closeModal();toast(`${config.title} ${editing?"updated":"created"}.`);await navigate(page);
      }catch(ex){out.textContent=ex.message;}
    });
  }
  async function loadResource(page, filters = {}) {
    const cfg=RESOURCE[page];
    const params = new URLSearchParams({limit:"200"});
    Object.entries(filters).forEach(([key,value])=>{ if(value!=="" && value!==null && value!==undefined) params.set(key,value); });
    const rows=await api(`${API_PREFIX}/${cfg.endpoint}?${params.toString()}`);
    state.cache[page]=rows;
    return rows;
  }
  function resourceFilterMarkup(page){
    const input=(label,id,placeholder="Enter value",type="number")=>`<label class="field">${label}<input id="${id}" type="${type}" placeholder="${placeholder}"></label>`;
    const select=(label,id,options)=>`<label class="field">${label}<select id="${id}"><option value="">All</option>${options.map(x=>`<option value="${x}">${x.replaceAll("_"," ")}</option>`).join("")}</select></label>`;
    let fields=input("Search text","filter-search","Search by name or title","search");
    if(page==="projects") fields+=input("Project ID","filter-record-id")+select("Project Status","filter-status",["ACTIVE","PLANNING","ON_HOLD","COMPLETED","CANCELLED"]);
    if(page==="tasks") fields+=input("Task ID","filter-record-id")+input("Project ID","filter-project-id")+select("Task Status","filter-status",["TODO","IN_PROGRESS","IN_REVIEW","DONE","BLOCKED"])+select("Priority","filter-priority",["LOW","MEDIUM","HIGH","URGENT"])+input("Assignee User ID","filter-assignee-id");
    if(page==="members") fields=input("Project ID","filter-project-id")+input("User ID","filter-user-id")+select("Project Role","filter-project-role",["MANAGER","LEAD","MEMBER"]);
    return `<div class="epms-filter-panel"><div class="epms-filter-grid">${fields}</div><div class="epms-filter-actions"><button id="apply-resource-filters" class="btn btn-primary" type="button">Apply Filters</button><button id="clear-resource-filters" class="btn btn-secondary" type="button">Clear</button></div></div>`;
  }
  async function renderResource(page) {
    const cfg=RESOURCE[page], root=$("#page-root"), policy=actionPolicy(page);
    const canCreate = !(state.roleName.toUpperCase()==="TEAM_LEAD" && ["projects","milestones"].includes(page));
    root.innerHTML=`<div class="panel"><div class="panel-head"><div><h2>${esc(cfg.title)}</h2><p class="muted">View and manage records according to your role permissions.</p></div>${canCreate?`<button id="add-record" class="btn btn-primary">+ Add ${esc(cfg.title.replace(/s$/,""))}</button>`:""}</div>${["projects","tasks","members"].includes(page)?resourceFilterMarkup(page):`<label class="field">Search ${esc(cfg.title.toLowerCase())}<input id="resource-search" type="search" placeholder="Search all ${esc(cfg.title.toLowerCase())} records..."></label>`}<div id="resource-content"><p class="muted">Loading…</p></div></div>`;
    if (canCreate) $("#add-record").addEventListener("click",()=>openRecordForm(page));
    try{
      let rows=await loadResource(page);
      const draw=()=>{
        const q=$("#resource-search")?.value.trim().toLowerCase() || "";
        const filtered=rows.filter(row=>Object.values(row).some(v=>String(v??"").toLowerCase().includes(q)));
        $("#resource-content").innerHTML=renderTable(filtered,cfg.columns,policy);
        $$(`[data-view]`,$("#resource-content")).forEach(btn=>btn.addEventListener("click",()=>openRecordView(page,filtered.find(r=>r.id===Number(btn.dataset.view)))));
        $$(`[data-edit]`,$("#resource-content")).forEach(btn=>btn.addEventListener("click",()=>{const record=filtered.find(r=>r.id===Number(btn.dataset.edit));if(page==="milestones" && state.roleName.toUpperCase()==="TEAM_LEAD") openMilestoneStatusForm(record);else openRecordForm(page,record);}));
        $$(`[data-delete]`,$("#resource-content")).forEach(btn=>btn.addEventListener("click",async()=>{
          const id=Number(btn.dataset.delete);if(!confirm(`Delete record #${id}?`))return;
          try{await api(`${API_PREFIX}/${cfg.endpoint}/${id}`,{method:"DELETE"});toast("Record deleted.");await navigate(page);}
          catch(ex){toast(ex.message,"error");}
        }));
      };
      if (["projects","tasks","members"].includes(page)) {
        const readFilters=()=>{
          const get=id=>document.getElementById(id)?.value?.trim() || "";
          const f={search:get("filter-search"),record_id:get("filter-record-id"),project_id:get("filter-project-id"),status:get("filter-status"),priority:get("filter-priority"),assignee_id:get("filter-assignee-id"),user_id:get("filter-user-id"),project_role:get("filter-project-role")};
          return Object.fromEntries(Object.entries(f).filter(([,v])=>v!==""));
        };
        $("#apply-resource-filters").addEventListener("click",async()=>{
          try{rows=await loadResource(page,readFilters());draw();}catch(ex){toast(ex.message,"error");}
        });
        $("#clear-resource-filters").addEventListener("click",async()=>{
          $$(".epms-filter-panel input, .epms-filter-panel select").forEach(el=>el.value="");
          try{rows=await loadResource(page);draw();}catch(ex){toast(ex.message,"error");}
        });
      } else $("#resource-search").addEventListener("input",draw);
      draw();
    }catch(ex){const content=$("#resource-content");content.innerHTML=`<div class="empty-state"><h3>Unable to load ${esc(cfg.title)}</h3><p>${esc(ex.message)}</p><small>Check your role permissions and API server.</small></div>`;}
  }


  async function renderComments() {
    const root = $("#page-root");
    root.innerHTML = `<div class="panel"><div class="panel-head"><div><h2>Comments</h2><p class="muted">Project and task conversations. Search and manage existing comments.</p></div></div><label class="field">Search comments<input id="comment-search" type="search" placeholder="Search comment text, task ID or user ID"></label><div id="comments-content">Loading…</div></div>`;
    try {
      const rows = await loadResource("comments");
      const draw = () => {
        const q = $("#comment-search").value.trim().toLowerCase();
        const filtered = rows.filter(r => [r.body,r.task_id,r.user_id,r.created_at].some(v => String(v ?? "").toLowerCase().includes(q)));
        $("#comments-content").innerHTML = renderTable(filtered, RESOURCE.comments.columns);
        $$(`[data-view]`).forEach(btn => btn.onclick = () => openRecordView("comments", rows.find(r => r.id === +btn.dataset.view)));
        $$(`[data-edit]`).forEach(btn => btn.onclick = () => openRecordForm("comments", rows.find(r => r.id === +btn.dataset.edit)));
        $$(`[data-delete]`).forEach(btn => btn.onclick = async () => {
          const id = +btn.dataset.delete;
          if (!confirm(`Delete comment #${id}?`)) return;
          try { await api(`${API_PREFIX}/comments/${id}`, {method:"DELETE"}); toast("Comment deleted."); await renderComments(); }
          catch (e) { toast(e.message,"error"); }
        });
      };
      $("#comment-search").oninput = draw;
      draw();
    } catch (e) { $("#comments-content").innerHTML = `<div class="empty-state"><h3>Unable to load comments</h3><p>${esc(e.message)}</p></div>`; }
  }

  async function renderNotifications() {
    const root = $("#page-root");
    root.innerHTML = `<div class="panel"><div class="panel-head"><div><h2>Notifications</h2><p class="muted">Your workspace updates and alerts.</p></div><button id="refresh-notifications" class="btn btn-secondary">Refresh</button></div><div id="notification-summary" class="stats-grid"></div><label class="field">Search notifications<input id="notification-search" type="search" placeholder="Search title or message"></label><div id="notifications-content">Loading…</div></div>`;
    const load = async () => {
      try {
        await api(`${API_PREFIX}/notifications/deadline-reminders/check`, {method:"POST"});
        const rows = await api(`${API_PREFIX}/notifications?limit=200`);
        const unread = rows.filter(n => !n.is_read).length;
        $("#notification-summary").innerHTML = `<div class="stat-card"><small>Total notifications</small><strong>${rows.length}</strong></div><div class="stat-card"><small>Unread</small><strong>${unread}</strong></div>`;
        const draw = () => {
          const q = $("#notification-search").value.trim().toLowerCase();
          const filtered = rows.filter(n => [n.title,n.message,n.created_at].some(v => String(v??"").toLowerCase().includes(q)));
          $("#notifications-content").innerHTML = renderTable(filtered, RESOURCE.notifications.columns, {view:true,edit:false,delete:false});
          $$(`[data-view]`,$("#notifications-content")).forEach(btn => btn.onclick = () => openRecordView("notifications", filtered.find(r => r.id === +btn.dataset.view)));
          // Mark as read is the only permitted notification update for a regular user.
          $$("tbody tr",$("#notifications-content")).forEach((tr,index)=>{
            const row=filtered[index];
            if(row && !row.is_read){
              const action=tr.querySelector(".row-actions");
              if(action) action.insertAdjacentHTML("beforeend",`<button class="btn btn-secondary btn-sm" data-read="${row.id}">Mark read</button>`);
            }
          });
          $$(`[data-read]`,$("#notifications-content")).forEach(btn=>btn.onclick=async()=>{
            try{await api(`${API_PREFIX}/notifications/${btn.dataset.read}`,{method:"PATCH",body:JSON.stringify({is_read:true})});toast("Notification marked as read.");await load();}
            catch(e){toast(e.message,"error");}
          });
        };
        $("#notification-search").oninput=draw;
        if (!rows.length) $("#notifications-content").innerHTML = `<div class="empty-state"><h3>No notifications yet</h3><p>New workspace updates will appear here.</p></div>`;
        else draw();
      } catch(e) { $("#notifications-content").innerHTML = `<div class="empty-state"><h3>Unable to load notifications</h3><p>${esc(e.message)}</p></div>`; }
    };
    $("#refresh-notifications").onclick = load;
    await load();
  }


  async function renderAuditLogs() {
    const root = $("#page-root");
    root.innerHTML = `<div class="panel"><div class="panel-head"><div><h2>Audit logs</h2><p class="muted">Read-only record of important workspace activity.</p></div><button id="refresh-audit" class="btn btn-secondary">Refresh</button></div><label class="field">Search activity<input id="audit-search" type="search" placeholder="Search user, action, entity or details"></label><div id="audit-content">Loading…</div></div>`;
    try {
      const rows = await loadResource("audit_logs");
      const draw = () => {
        const q = $("#audit-search").value.trim().toLowerCase();
        const filtered = rows.filter(r => [r.user_id,r.action,r.entity_type,r.entity_id,r.details,r.created_at].some(v => String(v ?? "").toLowerCase().includes(q)));
        $("#audit-content").innerHTML = renderTable(filtered, RESOURCE.audit_logs.columns, {view:true,edit:false,delete:false});
        $$(`[data-view]`).forEach(btn => btn.onclick = () => openRecordView("audit_logs", rows.find(r => r.id === +btn.dataset.view)));
      };
      $("#audit-search").oninput = draw;
      $("#refresh-audit").onclick = () => navigate("audit_logs");
      draw();
    } catch(e) { $("#audit-content").innerHTML = `<div class="empty-state"><h3>Unable to load audit logs</h3><p>${esc(e.message)}</p></div>`; }
  }

  async function renderUsers() {
    const root=$("#page-root");
    root.innerHTML=`<div class="panel"><div class="panel-head"><div><h2>Users</h2><p class="muted">Admin-only account management.</p></div><button class="btn btn-primary" id="add-user">+ Add user</button></div><div id="users-content">Loading…</div></div>`;
    $("#add-user").onclick=()=>openUserForm();
    try{
      const users=await api(`${API_PREFIX}/users/`);
      root.querySelector("#users-content").innerHTML=renderTable(users,["id","employee_code","full_name","email","role_id","department_id","is_active"]);
      $$("[data-edit]").forEach(b=>b.onclick=()=>openUserForm(users.find(u=>u.id===+b.dataset.edit)));
      $$("[data-delete]").forEach(b=>b.onclick=async()=>{const id=+b.dataset.delete;if(!confirm(`Delete user #${id}?`))return;try{await api(`${API_PREFIX}/users/${id}`,{method:"DELETE"});toast("User deleted.");navigate("users");}catch(e){toast(e.message,"error");}});
    }catch(e){$("#users-content").innerHTML=`<p class="form-error">${esc(e.message)}</p>`;}
  }
  async function openUserForm(user=null) {
    let roles=[],departments=[];
    try{[roles,departments]=await Promise.all([api(`${API_PREFIX}/roles?limit=200`),api(`${API_PREFIX}/departments?limit=200`)]);}catch(e){toast(e.message,"error");return;}
    openModal(`<div class="modal-head"><h3>${user?"Edit":"Create"} user</h3><button class="modal-close" data-close-modal>×</button></div>
      <form id="user-form" class="stack-form">
      <label class="field">Full name<input name="full_name" required minlength="2" value="${esc(user?.full_name)}"></label>
      <label class="field">Email<input name="email" type="email" required value="${esc(user?.email)}"></label>
      ${user?"":'<label class="field">Password<input name="password" type="password" minlength="8" required></label>'}
      <label class="field">Role<select name="role_id" required>${roles.map(r=>`<option value="${r.id}" ${r.id===user?.role_id?"selected":""}>${esc(r.name)}</option>`).join("")}</select></label>
      <label class="field">Department<select name="department_id"><option value="">None</option>${departments.map(d=>`<option value="${d.id}" ${d.id===user?.department_id?"selected":""}>${esc(d.name)}</option>`).join("")}</select></label>
      ${user?`<label class="field">Active<select name="is_active"><option value="true" ${user.is_active?"selected":""}>Active</option><option value="false" ${!user.is_active?"selected":""}>Inactive</option></select></label>`:""}
      <div id="user-error" class="form-error"></div><div class="modal-actions"><button type="button" class="btn btn-secondary" data-close-modal>Cancel</button><button class="btn btn-primary">Save</button></div></form>`);
    $("#user-form").onsubmit=async e=>{
      e.preventDefault();const f=e.currentTarget,p={full_name:f.full_name.value.trim(),email:f.email.value.trim(),role_id:+f.role_id.value,department_id:f.department_id.value?+f.department_id.value:null};
      if(!user)p.password=f.password.value;else{p.is_active=f.is_active.value==="true";}
      try{await api(`${API_PREFIX}/users/${user?user.id:""}`,{method:user?"PATCH":"POST",body:JSON.stringify(p)});closeModal();toast("User saved.");navigate("users");}
      catch(ex){$("#user-error").textContent=ex.message;}
    };
  }

  async function renderRoles() {
    const root=$("#page-root");
    root.innerHTML=`<div class="grid-two"><div class="panel"><div class="panel-head"><h2>Roles</h2></div><div id="roles-content">Loading…</div></div><div class="panel"><div class="panel-head"><h2>Permission assignments</h2></div><div id="role-perms">Select a role to view its permissions.</div></div></div>`;
    try{
      const [roles,permissions,assignments]=await Promise.all([api(`${API_PREFIX}/roles?limit=200`),api(`${API_PREFIX}/permissions/`),api(`${API_PREFIX}/role-permissions/`)]);
      $("#roles-content").innerHTML=renderTable(roles,["id","name","description"],false);
      $("#role-perms").innerHTML=`<label class="field">Choose role<select id="role-choice">${roles.map(r=>`<option value="${r.id}">${esc(r.name)}</option>`).join("")}</select></label><div id="permission-list"></div>`;
      const draw=()=>{const rid=+$("#role-choice").value,assigned=assignments.filter(a=>a.role_id===rid);
        $("#permission-list").innerHTML=permissions.map(p=>{const a=assigned.find(x=>x.permission_id===p.id);return `<div class="permission-row"><label><input type="checkbox" data-permission="${p.id}" ${a?"checked":""}> ${esc(p.code)}</label><small>${esc(p.description||"")}</small></div>`;}).join("");};
      $("#role-choice").onchange=draw;draw();
      $$("[data-permission]").forEach(()=>{});
      $("#permission-list").addEventListener("change",async e=>{const input=e.target.closest("[data-permission]");if(!input)return;const rid=+$("#role-choice").value,pid=+input.dataset.permission;const old=assignments.find(a=>a.role_id===rid&&a.permission_id===pid);
        try{if(input.checked){const a=await api(`${API_PREFIX}/role-permissions/`,{method:"POST",body:JSON.stringify({role_id:rid,permission_id:pid})});assignments.push(a);}else if(old){await api(`${API_PREFIX}/role-permissions/${old.id}`,{method:"DELETE"});assignments.splice(assignments.indexOf(old),1);}toast("Permissions updated.");}
        catch(ex){input.checked=!input.checked;toast(ex.message,"error");}});
    }catch(e){root.innerHTML=`<div class="panel"><p class="form-error">${esc(e.message)}</p></div>`;}
  }

  async function renderDashboard() {
    const root=$("#page-root");
    root.innerHTML=`<div class="stats-grid"><div class="stat-card"><small>Total projects</small><strong id="stat-projects">—</strong></div><div class="stat-card"><small>Total tasks</small><strong id="stat-tasks">—</strong></div><div class="stat-card"><small>Completed tasks</small><strong id="stat-done">—</strong></div><div class="stat-card"><small>Milestones</small><strong id="stat-milestones">—</strong></div><div class="stat-card"><small>Active projects</small><strong id="stat-active">—</strong></div><div class="stat-card"><small>Pending tasks</small><strong id="stat-pending">—</strong></div><div class="stat-card"><small>Overdue tasks</small><strong id="stat-overdue">—</strong></div><div class="stat-card"><small>Completed projects</small><strong id="stat-completed-projects">—</strong></div></div><div class="grid-two"><div class="panel"><div class="panel-head"><h2>Recent projects</h2><button class="btn btn-secondary btn-sm" data-go="projects">View all</button></div><div id="dash-projects">Loading…</div></div><div class="panel"><div class="panel-head"><h2>Task status</h2><button class="btn btn-secondary btn-sm" data-go="tasks">View tasks</button></div><div id="dash-tasks">Loading…</div></div></div>`;
    $$("[data-go]").forEach(b=>b.onclick=()=>navigate(b.dataset.go));
    const results=await Promise.allSettled([api(`${API_PREFIX}/projects?limit=200`),api(`${API_PREFIX}/tasks?limit=200`),api(`${API_PREFIX}/milestones?limit=200`),api(`${API_PREFIX}/analytics/dashboard`)]);
    const projects=results[0].status==="fulfilled"?results[0].value:[];
    const tasks=results[1].status==="fulfilled"?results[1].value:[];
    const milestones=results[2].status==="fulfilled"?results[2].value:[];
    const analyticsData=results[3].status==="fulfilled"?results[3].value:null;
    const summary=analyticsData?.summary||{};
    $("#stat-projects").textContent=analyticsData?summary.total_projects:"—";
    $("#stat-tasks").textContent=analyticsData?summary.total_tasks:"—";
    $("#stat-done").textContent=analyticsData?summary.completed_tasks:"—";
    $("#stat-milestones").textContent=analyticsData?summary.total_milestones:"—";
    $("#stat-active").textContent=analyticsData?summary.active_projects:"—";
    $("#stat-pending").textContent=analyticsData?summary.pending_tasks:"—";
    $("#stat-overdue").textContent=analyticsData?summary.overdue_tasks:"—";
    $("#stat-completed-projects").textContent=analyticsData?summary.completed_projects:"—";
    $("#dash-projects").innerHTML=results[0].status==="fulfilled"?renderTable(projects.slice(0,5),["id","name","status"],false):`<p class="form-error">${esc(results[0].reason.message)}</p>`;
    $("#dash-tasks").innerHTML=results[1].status==="fulfilled"?renderTable(tasks.slice(0,6),["id","title","status","priority"],false):`<p class="form-error">${esc(results[1].reason.message)}</p>`;

    // Visual analytics: task status and project status bar charts.
    const taskStatuses=["TODO","IN_PROGRESS","IN_REVIEW","DONE","BLOCKED"];
    const taskColors=["#8da6c9","#4f8cff","#9b7cf6","#21b88a","#ed7185"];
    const taskCounts=taskStatuses.map(s=>analyticsData?.task_status?.find(x=>String(x.status).toUpperCase()===s)?.count||0);
    const maxTask=Math.max(1,...taskCounts);
    const projectStatuses=["PLANNING","ACTIVE","ON_HOLD","COMPLETED","CANCELLED"];
    const projectColors=["#8da6c9","#21b88a","#edb34d","#4f8cff","#ed7185"];
    const projectCounts=projectStatuses.map(s=>analyticsData?.project_status?.find(x=>String(x.status).toUpperCase()===s)?.count||0);
    const maxProject=Math.max(1,...projectCounts);
    const chartCard=(title,subtitle,labels,counts,colors,max)=>`
      <section class="analytics-card">
        <div class="analytics-heading"><div><h3>${title}</h3><p>${subtitle}</p></div><span class="analytics-total">${counts.reduce((a,b)=>a+b,0)}<small> total</small></span></div>
        <div class="bar-chart" role="img" aria-label="${title}">
          ${labels.map((label,i)=>`<div class="bar-column"><div class="bar-value">${counts[i]}</div><div class="bar-track"><div class="bar-fill" style="height:${Math.max(counts[i] ? 8 : 3, counts[i]/max*100)}%;background:${colors[i]}"></div></div><div class="bar-label">${label.replace("_"," ")}</div></div>`).join("")}
        </div>
        <div class="chart-legend">${labels.map((label,i)=>`<span><i style="background:${colors[i]}"></i>${label.replace("_"," ")} <b>${counts[i]}</b></span>`).join("")}</div>
      </section>`;
    const analytics=document.createElement("div");
    analytics.className="analytics-grid";
    analytics.innerHTML=chartCard("Task progress","Tasks grouped by current status",taskStatuses,taskCounts,taskColors,maxTask)
      +chartCard("Project portfolio","Projects grouped by lifecycle",projectStatuses,projectCounts,projectColors,maxProject);
    if(analyticsData===null){analytics.innerHTML += `<section class="analytics-card"><p class="form-error">Advanced analytics could not be loaded: ${esc(results[3].reason?.message||"API unavailable")}</p></section>`;}
    const extra=document.createElement("div"); extra.className="analytics-grid";
    const workload=analyticsData?.employee_workload||[];
    const workloadMax=Math.max(1,...workload.map(x=>x.tasks));
    extra.innerHTML=`<section class="analytics-card"><div class="analytics-heading"><div><h3>Employee workload</h3><p>Assigned tasks by employee</p></div></div><div class="chart-legend">${workload.length?workload.map(x=>`<span>${esc(x.employee)} <b>${x.tasks}</b></span>`).join(""):`<span>No workload data</span>`}</div></section>`
      +`<section class="analytics-card"><div class="analytics-heading"><div><h3>Performance snapshot</h3><p>Additional task and project indicators</p></div></div><div class="chart-legend"><span>Active projects <b>${summary.active_projects??"—"}</b></span><span>Pending tasks <b>${summary.pending_tasks??"—"}</b></span><span>Overdue tasks <b>${summary.overdue_tasks??"—"}</b></span><span>Completed projects <b>${summary.completed_projects??"—"}</b></span></div></section>`;
    root.appendChild(analytics); root.appendChild(extra);
    const monthly=analyticsData?.monthly_performance||[];
    const monthlyCard=document.createElement("section"); monthlyCard.className="analytics-card";
    monthlyCard.innerHTML=`<div class="analytics-heading"><div><h3>Monthly performance</h3><p>Tasks created and completed over the recent six-month period</p></div></div><div class="chart-legend">${monthly.length?monthly.map(x=>`<span>${esc(x.month)} · Created <b>${x.created}</b> · Completed <b>${x.completed}</b></span>`).join(""):`<span>No monthly activity data</span>`}</div>`;
    root.appendChild(monthlyCard);
  }


  async function renderTaskChat(){
    const root=$("#page-root");
    root.innerHTML=`<div class="panel"><div class="panel-head"><div><h2>Task Conversation</h2><p class="muted">The project PM, Team Lead and assigned employee can collaborate here.</p></div><select id="task-chat-select" class="chat-project-select"><option value="">Select task</option></select></div><div id="task-chat-area" class="chat-area"><div class="empty-state">Select an assigned task to open its conversation.</div></div></div>`;
    try{const tasks=await api(`${API_PREFIX}/chat/tasks/eligible`);$("#task-chat-select").innerHTML='<option value="">Select task</option>'+tasks.map(t=>`<option value="${t.id}">#${t.id} · ${esc(t.title)} — ${esc(t.project_name)}</option>`).join("");
      $("#task-chat-select").onchange=()=>{if($("#task-chat-select").value)openTaskConversation(+$("#task-chat-select").value);};
      if(!tasks.length)$("#task-chat-area").innerHTML='<div class="empty-state">No task conversations are available. Employees will see tasks assigned to them; Team Leads will see tasks in projects where they are listed as LEAD.</div>';
    }catch(e){$("#task-chat-area").innerHTML=`<p class="form-error">${esc(e.message)}</p>`;}
  }
  async function openTaskConversation(taskId){
    const area=$("#task-chat-area");
    try{const data=await api(`${API_PREFIX}/chat/tasks/${taskId}/messages`);
      area.innerHTML=`<div class="chat-toolbar"><div><strong>${esc(data.task_title)}</strong><small>${esc(data.project_name)} · Task #${data.task_id}</small></div></div><div id="task-chat-messages" class="chat-messages"></div><div id="task-chat-replying" class="chat-replying"></div><form id="task-chat-compose" class="chat-compose"><textarea name="body" rows="2" placeholder="Write a task-related message…" required></textarea><div class="chat-compose-actions"><label class="btn btn-secondary btn-sm chat-file-label">Attach file<input id="task-chat-file" type="file" accept="image/*,.pdf,.doc,.docx,.xls,.xlsx" hidden></label><span class="muted">10 MB max</span><button class="btn btn-primary">Send</button></div></form>`;
      const box=$("#task-chat-messages");box.innerHTML=data.messages.map(taskMessageHtml).join("");bindTaskMessageActions(taskId);
      $("#task-chat-compose").onsubmit=async e=>{e.preventDefault();const form=e.currentTarget,body=form.body.value.trim();if(!body)return;try{const msg=await api(`${API_PREFIX}/chat/tasks/${taskId}/messages`,{method:"POST",body:JSON.stringify({body,reply_to_id:form.dataset.replyTo?+form.dataset.replyTo:null})});const file=$("#task-chat-file").files[0];if(file){const fd=new FormData();fd.append("file",file);await api(`${API_PREFIX}/chat/tasks/${taskId}/attachments?message_id=${msg.id}`,{method:"POST",body:fd});}await openTaskConversation(taskId);}catch(ex){toast(ex.message,"error");}};
    }catch(e){area.innerHTML=`<div class="empty-state"><h3>Conversation unavailable</h3><p>${esc(e.message)}</p></div>`;}
  }
  function taskMessageHtml(m){return `<article class="chat-message ${m.is_own?"own":""}" data-task-message-id="${m.id}"><div class="chat-message-head"><b>${esc(m.sender_name)}</b><time>${esc(m.created_at||"")}${m.edited_at?" · edited":""}${m.is_own?` · seen by ${m.read_count||0}`:""}</time></div>${m.reply_preview?`<blockquote>${esc(m.reply_preview)}</blockquote>`:""}<p>${esc(m.body)}</p>${(m.attachments||[]).map(a=>`<a class="chat-attachment" href="${API_BASE}/api/v1${a.url}" target="_blank" rel="noopener">📎 ${esc(a.name)}</a>`).join("")}<div class="chat-message-actions"><button data-task-reply="${m.id}">Reply</button>${m.is_own?`<button data-task-edit="${m.id}">Edit</button><button data-task-delete="${m.id}">Delete</button>`:""}</div></article>`;}
  function bindTaskMessageActions(taskId){
    $$('[data-task-reply]').forEach(b=>b.onclick=()=>{$("#task-chat-replying").textContent=`Replying to message #${b.dataset.taskReply}`;$("#task-chat-compose").dataset.replyTo=b.dataset.taskReply;});
    $$('[data-task-edit]').forEach(b=>b.onclick=async()=>{const article=b.closest("[data-task-message-id]"),old=article.querySelector("p")?.textContent||"",body=prompt("Edit your message",old);if(body===null||!body.trim())return;try{await api(`${API_PREFIX}/chat/task-messages/${b.dataset.taskEdit}`,{method:"PATCH",body:JSON.stringify({body})});await openTaskConversation(taskId);}catch(e){toast(e.message,"error");}});
    $$('[data-task-delete]').forEach(b=>b.onclick=async()=>{if(!confirm("Delete your message?"))return;try{await api(`${API_PREFIX}/chat/task-messages/${b.dataset.taskDelete}`,{method:"DELETE"});await openTaskConversation(taskId);}catch(e){toast(e.message,"error");}});
  }

  let chatSocket=null, chatProjectId=null, chatMembers=[];
  async function renderChat(){
    if(chatSocket){try{chatSocket.close();}catch{}chatSocket=null;}
    const root=$("#page-root"); root.innerHTML=`<div class="panel"><div class="panel-head"><div><h2>Project Group Chat</h2><p class="muted">One group conversation for each project.</p></div><select id="chat-project-select" class="chat-project-select"><option value="">Select project</option></select></div><div id="chat-area" class="chat-area"><div class="empty-state">Select a project to open its group chat.</div></div></div>`;
    try{
      const projects=await api(`${API_PREFIX}/projects?limit=200`);
      $("#chat-project-select").innerHTML='<option value="">Select project</option>'+projects.map(p=>`<option value="${p.id}">${esc(p.name)} (#${p.id})</option>`).join("");
      $("#chat-project-select").onchange=()=>{if($("#chat-project-select").value) openProjectChat(+$("#chat-project-select").value);};
    }catch(e){$("#chat-area").innerHTML=`<p class="form-error">${esc(e.message)}</p>`;}
  }
  async function openProjectChat(projectId,beforeId=null,append=false){
    chatProjectId=projectId;
    try{
      const data=await api(`${API_PREFIX}/chat/projects/${projectId}${beforeId?`?before_id=${beforeId}&limit=20`:"?limit=20"}`);
      chatMembers=data.members||[];
      const area=$("#chat-area");
      if(!append){
        area.innerHTML=`<div class="chat-toolbar"><div><strong>${esc(data.project_name)}</strong><small>${chatMembers.length} group members · ${data.unread_count||0} unread</small></div><div class="chat-toolbar-actions">${data.can_manage_members?'<button class="btn btn-secondary btn-sm" id="chat-manage-members">Manage members</button>':""}</div></div><div id="chat-messages" class="chat-messages"></div><div id="chat-typing" class="chat-typing"></div><form id="chat-compose" class="chat-compose"><div id="chat-replying" class="chat-replying"></div><textarea name="body" rows="2" placeholder="Write a message… Use @name to mention" required></textarea><div class="chat-compose-actions"><label class="btn btn-secondary btn-sm chat-file-label">Attach file<input id="chat-file" type="file" accept="image/*,.pdf,.doc,.docx,.xls,.xlsx" hidden></label><span class="muted">10 MB max</span><button class="btn btn-primary">Send</button></div></form>`;
        if(data.can_manage_members) $("#chat-manage-members").onclick=()=>manageChatMembers(projectId,data);
        const form=$("#chat-compose"); let replyId=null;
        form.onsubmit=async e=>{e.preventDefault();const body=form.body.value.trim();if(!body)return;try{const msg=await api(`${API_PREFIX}/chat/projects/${projectId}/messages`,{method:"POST",body:JSON.stringify({body,reply_to_id:form.dataset.replyTo?Number(form.dataset.replyTo):null})});form.body.value="";form.dataset.replyTo="";$("#chat-replying").textContent="";await attachPendingFile(projectId,msg.id);await openProjectChat(projectId);}catch(ex){toast(ex.message,"error");}};
        form.body.addEventListener("input",()=>{if(chatSocket?.readyState===1)chatSocket.send(JSON.stringify({type:"typing",is_typing:!!form.body.value.trim()}));});
        area.dataset.hasOlder=data.has_older?"1":"0";
        area.insertAdjacentHTML("afterbegin",data.has_older?'<button id="chat-load-older" class="btn btn-secondary btn-sm">Load older messages</button>':"");
        if(data.has_older)$("#chat-load-older").onclick=async()=>{const first=$("#chat-messages").querySelector("[data-message-id]");if(first)await openProjectChat(projectId,+first.dataset.messageId,true);};
        const wsUrl=`ws://127.0.0.1:8000/api/v1/chat/ws/${projectId}?token=${encodeURIComponent(state.token)}`;
        chatSocket=new WebSocket(wsUrl);
        chatSocket.onmessage=ev=>{const event=JSON.parse(ev.data);if(event.type==="typing"&&event.user_id!==state.user?.id){$("#chat-typing").textContent=event.is_typing?`${event.name} is typing…`:"";}if(event.type==="message"&&event.message.sender_id!==state.user?.id){toast(`New message from ${event.message.sender_name}`);const box=$("#chat-messages");if(box&&!box.querySelector(`[data-message-id="${event.message.id}"]`)){box.insertAdjacentHTML("beforeend",chatMessageHtml(event.message));bindChatMessageActions(projectId);}}};
      }
      const box=$("#chat-messages");
      const html=data.messages.map(m=>chatMessageHtml(m)).join("");
      if(append){box.insertAdjacentHTML("afterbegin",html);const first=box.firstElementChild;bindChatMessageActions(projectId);}
      else {box.innerHTML=html;bindChatMessageActions(projectId);}
    }catch(e){$("#chat-area").innerHTML=`<div class="empty-state"><h3>Chat unavailable</h3><p>${esc(e.message)}</p><small>Only members of this project's chat can open it.</small></div>`;}
  }
  function chatMessageHtml(m){return `<article class="chat-message ${m.is_own?"own":""}" data-message-id="${m.id}"><div class="chat-message-head"><b>${esc(m.sender_name)}</b><time>${esc(m.created_at||"")}${m.edited_at?" · edited":""}${m.is_own?` · seen by ${m.read_count||0}`:""}</time></div>${m.reply_preview?`<blockquote>${esc(m.reply_preview)}</blockquote>`:""}<p>${esc(m.body)}</p>${(m.attachments||[]).map(a=>`<a class="chat-attachment" href="${API_BASE}/api/v1${a.url}" target="_blank" rel="noopener">📎 ${esc(a.name)}</a>`).join("")}<div class="chat-message-actions"><button data-chat-reply="${m.id}">Reply</button>${m.is_own?`<button data-chat-edit="${m.id}">Edit</button><button data-chat-delete="${m.id}">Delete</button>`:""}</div></article>`;}
  function bindChatMessageActions(projectId){
    $$('[data-chat-reply]').forEach(b=>b.onclick=()=>{$("#chat-replying").textContent=`Replying to message #${b.dataset.chatReply} (send with reply reference)`;$("#chat-compose").dataset.replyTo=b.dataset.chatReply;});
    $$('[data-chat-edit]').forEach(b=>b.onclick=async()=>{const article=b.closest("[data-message-id]"),old=article.querySelector("p")?.textContent||"",body=prompt("Edit your message",old);if(body===null||!body.trim())return;try{await api(`${API_PREFIX}/chat/messages/${b.dataset.chatEdit}`,{method:"PATCH",body:JSON.stringify({body})});await openProjectChat(projectId);}catch(e){toast(e.message,"error");}});
    $$('[data-chat-delete]').forEach(b=>b.onclick=async()=>{if(!confirm("Delete your message?"))return;try{await api(`${API_PREFIX}/chat/messages/${b.dataset.chatDelete}`,{method:"DELETE"});await openProjectChat(projectId);}catch(e){toast(e.message,"error");}});
  }
  async function attachPendingFile(projectId,messageId){const file=$("#chat-file")?.files?.[0];if(!file)return;const form=new FormData();form.append("file",file);await api(`${API_PREFIX}/chat/projects/${projectId}/attachments?message_id=${messageId}`,{method:"POST",body:form});}
  async function manageChatMembers(projectId,data){
    const users=await api(`${API_PREFIX}/chat/projects/${projectId}/eligible-members`);
    const current=new Set(data.members.map(m=>m.user_id));
    const candidates=users;
    openModal(`<div class="modal-head"><h3>Manage group members</h3><button class="modal-close" data-close-modal>×</button></div><div class="stack-form"><p class="muted">Only the Project Manager can add or remove members.</p><label class="field">Add project member<select id="chat-add-user"><option value="">Select employee</option>${candidates.filter(u=>!current.has(u.id)).map(u=>`<option value="${u.id}">${esc(u.full_name)}</option>`).join("")}</select></label><button id="chat-add-member" class="btn btn-primary">Add member</button><div class="table-wrap"><table class="data-table"><tbody>${data.members.map(m=>`<tr><td>${esc(m.full_name)}</td><td>${esc(m.role)}</td><td>${m.user_id===state.user?.id?"You":`<button class="btn btn-danger btn-sm" data-remove-chat-member="${m.user_id}">Remove</button>`}</td></tr>`).join("")}</tbody></table></div></div>`);
    $("#chat-add-member").onclick=async()=>{const id=+$("#chat-add-user").value;if(!id)return;try{await api(`${API_PREFIX}/chat/projects/${projectId}/members`,{method:"POST",body:JSON.stringify({user_id:id})});closeModal();await openProjectChat(projectId);toast("Member added.");}catch(e){toast(e.message,"error");}};
    $$('[data-remove-chat-member]').forEach(b=>b.onclick=async()=>{try{await api(`${API_PREFIX}/chat/projects/${projectId}/members/${b.dataset.removeChatMember}`,{method:"DELETE"});closeModal();await openProjectChat(projectId);toast("Member removed.");}catch(e){toast(e.message,"error");}});
  }

  async function renderCompletedWork(){
    const root=$("#page-root");
    root.innerHTML=`<div class="stats-grid"><div class="stat-card"><small>Completed tasks</small><strong id="cw-tasks">—</strong></div><div class="stat-card"><small>Completed projects</small><strong id="cw-projects">—</strong></div></div><div class="grid-two"><div class="panel"><div class="panel-head"><h2>Completed Tasks</h2></div><div id="cw-task-list">Loading…</div></div><div class="panel"><div class="panel-head"><h2>Completed Projects</h2></div><div id="cw-project-list">Loading…</div></div></div>`;
    try{const data=await api(`${API_PREFIX}/completed-work`);$("#cw-tasks").textContent=data.summary.completed_tasks;$("#cw-projects").textContent=data.summary.completed_projects;
      const tasks=data.tasks||[],projects=data.projects||[];
      $("#cw-task-list").innerHTML=tasks.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Task</th><th>Project</th><th>Assigned to</th><th>Completed by</th><th>Completed at</th></tr></thead><tbody>${tasks.map(t=>`<tr><td>${esc(t.title)}</td><td>${esc(t.project_name)}</td><td>${esc(t.assignee||"—")}</td><td>${esc(t.completed_by||"—")}</td><td>${esc(t.completed_at?new Date(t.completed_at).toLocaleString():"—")}</td></tr>`).join("")}</tbody></table></div>`:`<div class="empty-state">No completed tasks yet.</div>`;
      $("#cw-project-list").innerHTML=projects.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Project</th><th>Completed by</th><th>Completed at</th></tr></thead><tbody>${projects.map(p=>`<tr><td>${esc(p.name)}</td><td>${esc(p.completed_by||"—")}</td><td>${esc(p.completed_at?new Date(p.completed_at).toLocaleString():"—")}</td></tr>`).join("")}</tbody></table></div>`:`<div class="empty-state">No completed projects yet.</div>`;
    }catch(e){root.innerHTML=`<div class="panel"><p class="form-error">${esc(e.message)}</p></div>`;}
  }

  async function navigate(page) {
    if(!PAGE[page]) page="dashboard";
    state.currentPage=page;
    const [title,eyebrow,subtitle]=PAGE[page];
    $("#crumb-current").textContent=title;$("#page-title").textContent=title;
    $("#page-eyebrow").textContent=eyebrow;$("#page-subtitle").textContent=subtitle;
    $$(".nav-link[data-page]").forEach(b=>b.classList.toggle("active",b.dataset.page===page));
    $("#sidebar").classList.remove("sidebar-open");
    $("#page-actions").innerHTML="";
    try{
      if(page==="dashboard") await renderDashboard();
      else if(page==="completed_work") await renderCompletedWork();
      else if(page==="users") await renderUsers();
      else if(page==="roles") await renderRoles();
      else if(page==="chat") await renderChat();
      else if(page==="task_chat") await renderTaskChat();
      else if(page==="comments") await renderComments();
      else if(page==="notifications") await renderNotifications();
      else if(page==="audit_logs") await renderAuditLogs();
      else if(RESOURCE[page]) await renderResource(page);
      else $("#page-root").innerHTML=`<div class="panel"><p>Page not available.</p></div>`;
    }catch(e){$("#page-root").innerHTML=`<div class="panel"><p class="form-error">${esc(e.message)}</p></div>`;}
  }

  function toggleTheme() {
    const html=document.documentElement, next=html.dataset.theme==="dark"?"light":"dark";
    html.dataset.theme=next;localStorage.setItem("epms_theme",next);
  }
  function init() {
    const savedTheme=localStorage.getItem("epms_theme");
    if(savedTheme)document.documentElement.dataset.theme=savedTheme;
    $("#login-form").addEventListener("submit",async e=>{
      e.preventDefault();const err=$("#login-error");err.textContent="";
      const btn=e.currentTarget.querySelector('[type="submit"]');btn.disabled=true;
      try{await login($("#login-email").value.trim(),$("#login-password").value);}
      catch(ex){err.textContent=ex.message;}
      finally{btn.disabled=false;}
    });
    $("#forgot-password-link").addEventListener("click",e=>{e.preventDefault();openForgotPassword();});
    const signup=document.createElement("a");signup.href="#";signup.id="signup-link";signup.textContent="Create an account";
    signup.style.display="block";signup.style.marginTop="14px";signup.style.textAlign="center";
    $("#login-form").querySelector(".login-foot").after(signup);
    signup.onclick=e=>{e.preventDefault();openSignup();};
    const companyLink=document.createElement("a");companyLink.href="#";companyLink.id="company-signup-link";companyLink.textContent="Register a company";companyLink.style.display="block";companyLink.style.marginTop="10px";companyLink.style.textAlign="center";$("#login-form").querySelector(".login-foot").after(companyLink);companyLink.onclick=e=>{e.preventDefault();openCompanySignup();};
    $("#toggle-password").onclick=()=>{const p=$("#login-password");p.type=p.type==="password"?"text":"password";};
    $("#login-theme-toggle").onclick=toggleTheme;$("#theme-toggle").onclick=toggleTheme;
    $("#logout-btn").onclick=()=>signOut();
    $("#main-nav").addEventListener("click",e=>{const b=e.target.closest("[data-page]");if(b)navigate(b.dataset.page);});
    $$("[data-page]").filter(el=>!$("#main-nav").contains(el)).forEach(b=>b.addEventListener("click",()=>navigate(b.dataset.page)));
    $("#menu-btn").onclick=()=>$("#sidebar").classList.add("sidebar-open");
    $("#sidebar-close").onclick=()=>$("#sidebar").classList.remove("sidebar-open");
    if(state.token){loadProfile().catch(()=>{setToken("");showLogin();});}else showLogin();
  }
  document.addEventListener("DOMContentLoaded",init);
})();