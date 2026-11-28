from __future__ import annotations
import os, re, uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import (User, Project, ProjectMember, ChatRoom, ChatRoomMember,
    ChatMessage, ChatMessageRead, ChatAttachment, Notification, Task, TaskConversationMessage, TaskConversationMessageRead, TaskConversationAttachment, AuditLog)
from app.routers.auth import get_current_user
from app.core.security import decode_access_token

router = APIRouter(prefix="/chat", tags=["Project Group Chat"])
UPLOAD_DIR = Path("/tmp/uploads/chat")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".doc", ".docx", ".xls", ".xlsx"}
MAX_FILE_SIZE = 10 * 1024 * 1024

class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    reply_to_id: Optional[int] = None

class MemberIn(BaseModel):
    user_id: int

class EditMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=10000)

class ConnectionHub:
    def __init__(self): self.rooms: dict[int, set[WebSocket]] = {}
    async def connect(self, room_id: int, ws: WebSocket):
        await ws.accept(); self.rooms.setdefault(room_id, set()).add(ws)
    def disconnect(self, room_id: int, ws: WebSocket):
        self.rooms.get(room_id, set()).discard(ws)
    async def broadcast(self, room_id: int, payload: dict):
        dead=[]
        for ws in list(self.rooms.get(room_id, set())):
            try: await ws.send_json(payload)
            except Exception: dead.append(ws)
        for ws in dead: self.disconnect(room_id, ws)

hub = ConnectionHub()

def role_name(user): return (user.role.name if user.role else "").upper().replace(" ", "_")
def is_pm(user, project, db):
    if role_name(user) != "PROJECT_MANAGER":
        return False
    if project.owner_id == user.id:
        return True
    member = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id))
    return bool(member and member.project_role.upper() in {"MANAGER", "PM"})

def get_project_room(db: Session, project_id: int, user: User):
    project = db.get(Project, project_id)
    if not project or project.company_id != user.company_id: raise HTTPException(404, "Project not found")
    room = db.scalar(select(ChatRoom).where(ChatRoom.project_id == project_id))
    if not room:
        if not is_pm(user, project, db):
            raise HTTPException(403, "Only the Project Manager can initialize this group chat")
        room = ChatRoom(project_id=project_id, created_by=user.id); db.add(room); db.flush()
        # Start with the project owner/PM only; PM explicitly manages all other chat members.
        db.add(ChatRoomMember(room_id=room.id, user_id=project.owner_id, added_by=user.id))
        db.commit(); db.refresh(room)
    membership = db.scalar(select(ChatRoomMember.id).where(ChatRoomMember.room_id == room.id, ChatRoomMember.user_id == user.id))
    if not membership: raise HTTPException(403, "You are not a member of this project group chat")
    return project, room

def serialize_message(db, m, current_user_id):
    sender = db.get(User, m.sender_id)
    reply = db.get(ChatMessage, m.reply_to_id) if m.reply_to_id else None
    reads = db.scalars(select(ChatMessageRead).where(ChatMessageRead.message_id == m.id)).all()
    attachments = db.scalars(select(ChatAttachment).where(ChatAttachment.message_id == m.id)).all()
    return {"id":m.id,"room_id":m.room_id,"sender_id":m.sender_id,"sender_name":sender.full_name if sender else "Unknown",
        "body":"[Message deleted]" if m.is_deleted else m.body,"reply_to_id":m.reply_to_id,
        "reply_preview":(reply.body[:180] if reply and not reply.is_deleted else None),
        "created_at":m.created_at.isoformat() if m.created_at else None,"edited_at":m.edited_at.isoformat() if m.edited_at else None,
        "is_own":m.sender_id==current_user_id,"read_by":[r.user_id for r in reads],"read_count":len(reads),
        "attachments":[{"id":a.id,"name":a.original_name,"size":a.size_bytes,"mime_type":a.mime_type,"url":f"/chat/attachments/{a.id}"} for a in attachments]}

@router.get("/projects/{project_id}")
def get_chat(project_id: int, before_id: Optional[int] = Query(None), limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project, room = get_project_room(db, project_id, user)
    stmt = select(ChatMessage).where(ChatMessage.room_id == room.id).order_by(desc(ChatMessage.id))
    if before_id: stmt = stmt.where(ChatMessage.id < before_id)
    msgs = list(reversed(db.scalars(stmt.limit(limit)).all()))
    # Mark fetched messages as read for this member.
    for m in msgs:
        if m.sender_id != user.id and not db.scalar(select(ChatMessageRead.id).where(ChatMessageRead.message_id == m.id, ChatMessageRead.user_id == user.id)):
            db.add(ChatMessageRead(message_id=m.id, user_id=user.id))
    db.commit()
    unread_count = len(db.scalars(select(ChatMessage.id).where(ChatMessage.room_id == room.id, ChatMessage.sender_id != user.id, ~ChatMessage.id.in_(select(ChatMessageRead.message_id).where(ChatMessageRead.user_id == user.id)))).all())
    members = db.execute(select(ChatRoomMember, User).join(User, User.id == ChatRoomMember.user_id).where(ChatRoomMember.room_id == room.id).order_by(User.full_name)).all()
    return {"room_id":room.id,"project_id":project.id,"project_name":project.name,"unread_count":unread_count,
        "can_manage_members":is_pm(user, project, db),
        "members":[{"user_id":m.user_id,"full_name":u.full_name,"role":u.role.name if u.role else ""} for m,u in members],
        "messages":[serialize_message(db,m,user.id) for m in msgs],"has_older":len(msgs)==limit}

@router.post("/projects/{project_id}/messages")
async def send_message(project_id: int, payload: MessageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project, room = get_project_room(db, project_id, user)
    if payload.reply_to_id:
        parent = db.get(ChatMessage, payload.reply_to_id)
        if not parent or parent.room_id != room.id: raise HTTPException(400, "Reply target is not in this group")
    msg = ChatMessage(room_id=room.id, sender_id=user.id, body=payload.body.strip(), reply_to_id=payload.reply_to_id)
    db.add(msg); db.flush()
    db.execute(text("SELECT setval(pg_get_serial_sequence('notifications','id'), GREATEST(COALESCE((SELECT MAX(id) FROM notifications), 1), 1), EXISTS (SELECT 1 FROM notifications))"))
    members = db.scalars(select(ChatRoomMember).where(ChatRoomMember.room_id == room.id, ChatRoomMember.user_id != user.id)).all()
    mentioned_ids=set()
    for m in re.finditer(r"@([\w .-]{2,80})", payload.body):
        name=m.group(1).strip()
        match=db.scalar(select(User).where(User.full_name.ilike(name), User.company_id == user.company_id))
        if match: mentioned_ids.add(match.id)
    for member in members:
        title = "You were mentioned" if member.user_id in mentioned_ids else f"New message in {project.name}"
        notification_message = f"{user.full_name}: {payload.body[:180]}"
        db.add(Notification(user_id=member.user_id,title=title,message=notification_message,is_read=False))
    db.add(AuditLog(user_id=user.id, action="CHAT_MESSAGE_SENT", entity_type="PROJECT", entity_id=project.id, details=f"Sent a message in project group chat #{project.id}"))
    db.commit(); db.refresh(msg)
    data=serialize_message(db,msg,user.id)
    await hub.broadcast(room.id,{"type":"message","message":data})
    return data

@router.patch("/messages/{message_id}")
def edit_message(message_id: int, payload: EditMessageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    msg=db.get(ChatMessage,message_id)
    if not msg: raise HTTPException(404,"Message not found")
    if msg.sender_id != user.id: raise HTTPException(403,"You can edit only your own messages")
    msg.body=payload.body.strip(); msg.edited_at=datetime.now(timezone.utc); db.commit(); db.refresh(msg)
    return serialize_message(db,msg,user.id)

@router.delete("/messages/{message_id}")
def delete_message(message_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    msg=db.get(ChatMessage,message_id)
    if not msg: raise HTTPException(404,"Message not found")
    if msg.sender_id != user.id: raise HTTPException(403,"You can delete only your own messages")
    msg.is_deleted=True; msg.body=""; db.commit(); return {"message":"Message deleted"}

@router.get("/projects/{project_id}/eligible-members")
def eligible_chat_members(project_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    project,room=get_project_room(db,project_id,user)
    rows=db.execute(select(User.id,User.full_name).join(ProjectMember,ProjectMember.user_id==User.id).where(ProjectMember.project_id==project_id,User.is_active.is_(True)).order_by(User.full_name)).all()
    return [{"id":r.id,"full_name":r.full_name} for r in rows]

@router.post("/projects/{project_id}/members")
def add_member(project_id: int, payload: MemberIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project,room=get_project_room(db,project_id,user)
    if not is_pm(user,project,db): raise HTTPException(403,"Only the Project Manager can add group members")
    is_project_member=db.scalar(select(ProjectMember.id).where(ProjectMember.project_id==project_id,ProjectMember.user_id==payload.user_id))
    if not is_project_member and project.owner_id != payload.user_id: raise HTTPException(400,"Only current project members can be added to the chat")
    if not db.scalar(select(User.id).where(User.id==payload.user_id, User.company_id==user.company_id)): raise HTTPException(404,"User not found")
    if db.scalar(select(ChatRoomMember.id).where(ChatRoomMember.room_id==room.id,ChatRoomMember.user_id==payload.user_id)): return {"message":"Already a group member"}
    db.add(ChatRoomMember(room_id=room.id,user_id=payload.user_id,added_by=user.id)); db.commit(); return {"message":"Member added"}

@router.delete("/projects/{project_id}/members/{user_id}")
def remove_member(project_id:int,user_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    project,room=get_project_room(db,project_id,user)
    if not is_pm(user,project,db): raise HTTPException(403,"Only the Project Manager can remove group members")
    if user_id==project.owner_id: raise HTTPException(400,"Project owner cannot be removed from the group")
    member=db.scalar(select(ChatRoomMember).where(ChatRoomMember.room_id==room.id,ChatRoomMember.user_id==user_id))
    if not member: raise HTTPException(404,"Chat member not found")
    db.delete(member); db.commit(); return {"message":"Member removed"}

@router.post("/projects/{project_id}/attachments")
def upload_attachment(project_id:int,message_id:int=Query(...),file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    project,room=get_project_room(db,project_id,user)
    msg=db.get(ChatMessage,message_id)
    if not msg or msg.room_id!=room.id or msg.sender_id!=user.id: raise HTTPException(403,"Attach files to your own message only")
    ext=Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT: raise HTTPException(415,"Allowed files: images, PDF, DOC/DOCX, XLS/XLSX")
    content=file.file.read(MAX_FILE_SIZE+1)
    if len(content)>MAX_FILE_SIZE: raise HTTPException(413,"Maximum file size is 10 MB")
    stored=f"{uuid.uuid4().hex}{ext}"; (UPLOAD_DIR/stored).write_bytes(content)
    item=ChatAttachment(message_id=msg.id,original_name=Path(file.filename).name,stored_name=stored,mime_type=file.content_type or "application/octet-stream",size_bytes=len(content),uploaded_by=user.id)
    db.add(item); db.commit(); db.refresh(item)
    return {"id":item.id,"name":item.original_name,"url":f"/api/v1/chat/attachments/{item.id}","size":item.size_bytes}

@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    from fastapi.responses import FileResponse
    item=db.get(ChatAttachment,attachment_id)
    if not item: raise HTTPException(404,"Attachment not found")
    msg=db.get(ChatMessage,item.message_id)
    membership=db.scalar(select(ChatRoomMember.id).where(ChatRoomMember.room_id==msg.room_id,ChatRoomMember.user_id==user.id))
    if not membership: raise HTTPException(403,"Not a chat member")
    path=UPLOAD_DIR/item.stored_name
    if not path.exists(): raise HTTPException(404,"File missing")
    return FileResponse(path,filename=item.original_name,media_type=item.mime_type)



def get_task_conversation_access(db: Session, task_id: int, user: User):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    project = db.get(Project, task.project_id)
    if not project or project.company_id != user.company_id:
        raise HTTPException(404, "Task not found")
    role = role_name(user)
    is_assignee = task.assignee_id == user.id and role in {"EMPLOYEE", "EMP"}
    lead_membership = db.scalar(select(ProjectMember.id).where(
        ProjectMember.project_id == task.project_id, ProjectMember.user_id == user.id,
        ProjectMember.project_role.in_(["LEAD", "TEAM_LEAD", "TL"])))
    is_team_lead = role in {"TEAM_LEAD", "TL"} and bool(lead_membership)
    is_project_manager = role in {"PROJECT_MANAGER", "PM"} and project.owner_id == user.id
    is_admin = role in {"ADMIN", "ADMINISTRATOR"}
    if not (is_assignee or is_team_lead or is_project_manager or is_admin):
        raise HTTPException(403, "Only the project PM, assigned Team Lead, and assigned Employee can access this task conversation")
    if not task.assignee_id:
        raise HTTPException(409, "Assign this task to an employee before starting its conversation")
    return task, project

def serialize_task_message(db: Session, msg: TaskConversationMessage, current_user_id: int):
    sender = db.get(User, msg.sender_id)
    reply = db.get(TaskConversationMessage, msg.reply_to_id) if msg.reply_to_id else None
    attachments = db.scalars(select(TaskConversationAttachment).where(TaskConversationAttachment.message_id == msg.id)).all()
    reads = db.scalars(select(TaskConversationMessageRead).where(TaskConversationMessageRead.message_id == msg.id)).all()
    return {"id": msg.id, "task_id": msg.task_id, "sender_id": msg.sender_id,
        "sender_name": sender.full_name if sender else "Unknown",
        "body": "[Message deleted]" if msg.is_deleted else msg.body,
        "reply_to_id": msg.reply_to_id, "reply_preview": reply.body[:160] if reply and not reply.is_deleted else None,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "edited_at": msg.edited_at.isoformat() if msg.edited_at else None, "is_own": msg.sender_id == current_user_id,
        "read_by": [x.user_id for x in reads], "read_count": len(reads),
        "attachments": [{"id": a.id, "name": a.original_name, "url": f"/chat/task-attachments/{a.id}"} for a in attachments]}

@router.get("/tasks/eligible")
def eligible_task_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    role = role_name(user)
    if role in {"EMPLOYEE", "EMP"}:
        rows = db.scalars(select(Task).where(Task.assignee_id == user.id).order_by(Task.id.desc())).all()
    elif role in {"TEAM_LEAD", "TL"}:
        rows = db.scalars(select(Task).join(ProjectMember, ProjectMember.project_id == Task.project_id).where(
            ProjectMember.user_id == user.id, ProjectMember.project_role.in_(["LEAD", "TEAM_LEAD", "TL"]), Task.assignee_id.is_not(None)).order_by(Task.id.desc())).all()
    elif role in {"PROJECT_MANAGER", "PM"}:
        rows = db.scalars(select(Task).join(Project, Project.id == Task.project_id).where(Project.owner_id == user.id, Task.assignee_id.is_not(None)).order_by(Task.id.desc())).all()
    elif role in {"ADMIN", "ADMINISTRATOR"}:
        rows = db.scalars(select(Task).join(Project, Project.id == Task.project_id).where(Project.company_id == user.company_id, Task.assignee_id.is_not(None)).order_by(Task.id.desc())).all()
    else:
        return []
    return [{"id": t.id, "title": t.title, "project_id": t.project_id, "project_name": t.project.name if t.project else "", "assignee_id": t.assignee_id} for t in rows]

@router.get("/tasks/{task_id}/messages")
def get_task_messages(task_id: int, before_id: Optional[int] = Query(None), limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task, project = get_task_conversation_access(db, task_id, user)
    stmt = select(TaskConversationMessage).where(TaskConversationMessage.task_id == task_id).order_by(desc(TaskConversationMessage.id))
    if before_id: stmt = stmt.where(TaskConversationMessage.id < before_id)
    messages = list(reversed(db.scalars(stmt.limit(limit)).all()))
    for message in messages:
        if message.sender_id != user.id and not db.scalar(select(TaskConversationMessageRead.id).where(TaskConversationMessageRead.message_id == message.id, TaskConversationMessageRead.user_id == user.id)):
            db.add(TaskConversationMessageRead(message_id=message.id, user_id=user.id))
    db.commit()
    return {"task_id": task.id, "task_title": task.title, "project_name": project.name, "messages": [serialize_task_message(db, m, user.id) for m in messages], "has_older": len(messages) == limit}

@router.post("/tasks/{task_id}/messages")
def send_task_message(task_id: int, payload: MessageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task, project = get_task_conversation_access(db, task_id, user)
    if payload.reply_to_id:
        parent = db.get(TaskConversationMessage, payload.reply_to_id)
        if not parent or parent.task_id != task_id: raise HTTPException(400, "Reply target is not in this task conversation")
    msg = TaskConversationMessage(task_id=task_id, sender_id=user.id, body=payload.body.strip(), reply_to_id=payload.reply_to_id)
    db.add(msg); db.flush()
    db.execute(text("SELECT setval(pg_get_serial_sequence('notifications','id'), GREATEST(COALESCE((SELECT MAX(id) FROM notifications), 1), 1), EXISTS (SELECT 1 FROM notifications))"))
    recipients = set()
    if task.assignee_id: recipients.add(task.assignee_id)
    recipients.add(project.owner_id)
    recipients.update(db.scalars(select(ProjectMember.user_id).where(ProjectMember.project_id == project.id, ProjectMember.project_role.in_(["LEAD", "TEAM_LEAD", "TL"]))).all())
    for recipient_id in recipients - {user.id}:
        db.add(Notification(user_id=recipient_id, title=f"New message about task #{task.id}", message=f"{user.full_name}: {payload.body[:160]}", is_read=False))
    from app.models.entities import AuditLog
    db.add(AuditLog(user_id=user.id, action="CHAT_MESSAGE_SENT", entity_type="TASK", entity_id=task.id, details=f"Sent a message in task conversation #{task.id}"))
    # Keep PostgreSQL's notification identity sequence aligned with existing rows.
    db.commit(); db.refresh(msg)
    return serialize_task_message(db, msg, user.id)

@router.patch("/task-messages/{message_id}")
def edit_task_message(message_id: int, payload: EditMessageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    msg = db.get(TaskConversationMessage, message_id)
    if not msg: raise HTTPException(404, "Message not found")
    get_task_conversation_access(db, msg.task_id, user)
    if msg.sender_id != user.id: raise HTTPException(403, "You can edit only your own messages")
    msg.body = payload.body.strip(); msg.edited_at = datetime.now(timezone.utc); db.commit(); db.refresh(msg)
    return serialize_task_message(db, msg, user.id)

@router.delete("/task-messages/{message_id}")
def delete_task_message(message_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    msg = db.get(TaskConversationMessage, message_id)
    if not msg: raise HTTPException(404, "Message not found")
    get_task_conversation_access(db, msg.task_id, user)
    if msg.sender_id != user.id: raise HTTPException(403, "You can delete only your own messages")
    msg.is_deleted = True; msg.body = ""; db.commit(); return {"message": "Message deleted"}

@router.post("/tasks/{task_id}/attachments")
def upload_task_attachment(task_id: int, message_id: int = Query(...), file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_task_conversation_access(db, task_id, user)
    msg = db.get(TaskConversationMessage, message_id)
    if not msg or msg.task_id != task_id or msg.sender_id != user.id: raise HTTPException(403, "Attach files to your own task message only")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT: raise HTTPException(415, "Allowed files: images, PDF, DOC/DOCX, XLS/XLSX")
    content = file.file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE: raise HTTPException(413, "Maximum file size is 10 MB")
    stored = f"{uuid.uuid4().hex}{ext}"; (UPLOAD_DIR / stored).write_bytes(content)
    item = TaskConversationAttachment(message_id=msg.id, original_name=Path(file.filename).name, stored_name=stored, mime_type=file.content_type or "application/octet-stream", size_bytes=len(content), uploaded_by=user.id)
    db.add(item); db.commit(); db.refresh(item)
    return {"id": item.id, "name": item.original_name, "url": f"/chat/task-attachments/{item.id}"}

@router.get("/task-attachments/{attachment_id}")
def download_task_attachment(attachment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from fastapi.responses import FileResponse
    item = db.get(TaskConversationAttachment, attachment_id)
    if not item: raise HTTPException(404, "Attachment not found")
    msg = db.get(TaskConversationMessage, item.message_id); get_task_conversation_access(db, msg.task_id, user)
    path = UPLOAD_DIR / item.stored_name
    if not path.exists(): raise HTTPException(404, "File missing")
    return FileResponse(path, filename=item.original_name, media_type=item.mime_type)

@router.websocket("/ws/{project_id}")
async def chat_ws(websocket:WebSocket,project_id:int,token:str=Query(...)):
    db=next(get_db())
    try:
        payload=decode_access_token(token); uid=int(payload.get("sub")); user=db.get(User,uid)
        if not user or not user.is_active: await websocket.close(code=4401); return
        project=db.get(Project,project_id)
        if not project or project.company_id != user.company_id: await websocket.close(code=4404); return
        room=db.scalar(select(ChatRoom).where(ChatRoom.project_id==project_id))
        if not room or not db.scalar(select(ChatRoomMember.id).where(ChatRoomMember.room_id==room.id,ChatRoomMember.user_id==uid)):
            await websocket.close(code=4403); return
        await hub.connect(room.id,websocket)
        while True:
            data=await websocket.receive_json()
            if data.get("type")=="typing": await hub.broadcast(room.id,{"type":"typing","user_id":uid,"name":user.full_name,"is_typing":bool(data.get("is_typing"))})
    except WebSocketDisconnect: pass
    except Exception: 
        try: await websocket.close(code=1011)
        except Exception: pass
    finally:
        try:
            if 'room' in locals(): hub.disconnect(room.id,websocket)
        except Exception: pass
        db.close()
